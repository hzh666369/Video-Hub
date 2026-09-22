import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from starlette.datastructures import MutableHeaders
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.access import router as access_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.heartbeat import router as heartbeat_router
from app.api.parse import router as parse_router
from app.api.records import router as records_router
from app.api.settings import router as settings_router
from app.api.stream import router as stream_router
from app.api.visits import router as visits_router
from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.services.client_ip import rate_limit_key
from app.services.proxy import close_shared_client
from app.services.ratelimit import health_limiter

logger = logging.getLogger("videohub")


def _ensure_columns() -> None:
    """轻量迁移：create_all 只建新表，不会给已存在的表补列，这里手动补。

    仅覆盖自研演进新增的列；列已存在时静默跳过。
    """
    from sqlalchemy import inspect

    with engine.begin() as conn:
        names = {c["name"] for c in inspect(engine).get_columns("users")}
        if "onboarding_completed" not in names:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN onboarding_completed BOOLEAN DEFAULT 0"))
            # 存量用户视为已完成引导，避免升级后老用户全员弹窗；仅新注册/新建用户会弹
            conn.execute(text("UPDATE users SET onboarding_completed = 1"))

        if "permissions" not in names:
            # SQLite ADD COLUMN 带 NOT NULL 必须同时给 DEFAULT,存量行自动补 "[]"
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN permissions VARCHAR(255) NOT NULL DEFAULT '[]'"))

        # TOTP 两步验证（S19）：存量库幂等补列；recovery_codes 表由 create_all 建
        if "totp_secret" not in names:
            conn.execute(text("ALTER TABLE users ADD COLUMN totp_secret VARCHAR(64)"))
        if "totp_enabled" not in names:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN DEFAULT 0"))
        if "totp_last_step" not in names:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN totp_last_step INTEGER DEFAULT 0"))

        rec_names = {c["name"] for c in inspect(engine).get_columns("records")}
        if "route_name" not in rec_names:
            conn.execute(text("ALTER TABLE records ADD COLUMN route_name VARCHAR(64)"))

    # users.username 判重口径为大小写不敏感（注册/建号/登录均按 lower() 比较），但模型
    # 唯一索引区分大小写：并发下 Alice/alice 可同时入库绕过判重（红线 3.1 要求 DB
    # 约束兜底）。补 NOCASE 唯一索引；存量若已有大小写变体重名会创建失败，此时仅记
    # 可操作日志并继续启动，需人工合并后重试。
    #
    # 下面每个 DDL 各自 try/except：早期版本两段都**没有内部 try**，第一个索引一旦失败
    # 就会抛穿整个 _ensure_columns（被 lifespan 的 except 吞掉后继续启动），于是第二个
    # ix_records_created_at 根本不会执行，而原注释却写「互不牵连」。现改为逐条隔离：
    # 任一条失败只影响它自己，并在日志里点名是哪条、需要人工处理什么。
    ddl_migrations = (
        ("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username_nocase "
         "ON users (username COLLATE NOCASE)",
         "users.username NOCASE 唯一索引（红线 3.1 的 DB 兜底）"),
        # 看板按 created_at 窗口统计 records（create_all 不会给已存在的表补索引）
        ("CREATE INDEX IF NOT EXISTS ix_records_created_at ON records (created_at)",
         "records.created_at 索引"),
    )
    for ddl, label in ddl_migrations:
        try:
            with engine.begin() as conn:
                conn.execute(text(ddl))
        except Exception:  # noqa: BLE001 — 单条迁移失败不阻断启动，也绝不牵连其余迁移
            logger.exception("补建 %s 失败，该约束/索引本轮缺位，需人工处理后重启", label)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    try:
        _ensure_columns()
    except Exception:  # noqa: BLE001 — 迁移失败不阻断启动，报错可见即可
        logger.exception("启动期轻量迁移 _ensure_columns 失败")
    with SessionLocal() as db:
        from app.services.auth import seed_admin

        generated = seed_admin(db)
        if generated:
            logger.warning(
                "已创建管理员账号 admin，初始密码见 backend/.env 的 VIDEOHUB_ADMIN_PASSWORD"
                "（也可用环境变量 VIDEOHUB_ADMIN_PASSWORD 自行指定后重建）")
    yield
    await close_shared_client()


class SecurityHeadersMiddleware:
    """S17：给所有响应补齐安全响应头（2026-09-18 外部安全评估"中危"项修复）。

    纯 ASGI 实现而非 BaseHTTPMiddleware：避免包裹 /api/stream 的流式响应（视频
    代理）带来的缓冲与兼容问题，只在 http.response.start 消息上原位改头。

    - HSTS 曾约定"由 Cloudflare 边缘负责"，但实测边缘并未下发（评估报告线上
      抓包缺该头），改为应用层统一补发：浏览器只信任 HTTPS 响应里的 STS 头，
      本地 http 调试不受影响，生产经隧道透传即生效。
    - CSP 的 frame-src 放行 https: 而非精确域名白名单：VIP 解析线路前缀由
      管理员随时增改（S9 只强制 https:// 开头），域名集是动态的，无法静态
      枚举；http 帧与所有非帧子资源仍被拒。
    - style-src 需要 'unsafe-inline'：Vue 模板大量使用内联 style 属性与运行时
      样式绑定（如 animation-delay），无法全部外置。
    - Permissions-Policy 刻意**不含** fullscreen / autoplay：VIP 播放器是跨域
      iframe，头策略若限 (self) 会连带掐掉 iframe 内的全屏与自动播放。
    """

    # 有序 (name, value) 列表；统一 setdefault，端点仍可按需覆盖
    _HEADERS = (
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
        ("Content-Security-Policy",
         "default-src 'self'; "
         "script-src 'self'; "
         "style-src 'self' 'unsafe-inline'; "
         "img-src 'self' data: blob:; "
         "media-src 'self'; "
         "font-src 'self' data:; "
         "connect-src 'self'; "
         "frame-src https:; "
         "object-src 'none'; "
         "base-uri 'self'; "
         "form-action 'self'; "
         "frame-ancestors 'none'; "
         "upgrade-insecure-requests"),
        ("Strict-Transport-Security", "max-age=31536000; includeSubDomains"),
        ("X-Frame-Options", "DENY"),
        ("Permissions-Policy",
         "camera=(), microphone=(), geolocation=(), payment=(), usb=(), display-capture=()"),
        ("Cross-Origin-Opener-Policy", "same-origin"),
        ("Cross-Origin-Resource-Policy", "same-origin"),
    )

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self._HEADERS:
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)


# API 文档端点（/docs /redoc /openapi.json）默认关闭：公网暴露下不应免费送出全量
# API 地图；本地调试可设 VIDEOHUB_DOCS=1 显式开启（2026-09-15 审计 L-1）
_ENABLE_DOCS = os.environ.get("VIDEOHUB_DOCS", "").strip() == "1"

app = FastAPI(
    title="VideoHub", lifespan=lifespan,
    docs_url="/docs" if _ENABLE_DOCS else None,
    redoc_url="/redoc" if _ENABLE_DOCS else None,
    openapi_url="/openapi.json" if _ENABLE_DOCS else None,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key or "dev-insecure-secret",
    same_site="lax",
    max_age=7 * 24 * 3600,  # 7 天免登录；到期重新登录换取新签名 Cookie
    https_only=settings.cookie_secure,  # 公网部署（VIDEOHUB_COOKIE_SECURE=1）时禁止 Cookie 走明文
)
app.include_router(auth_router)
app.include_router(parse_router)
app.include_router(records_router)
app.include_router(settings_router)
app.include_router(stream_router)
app.include_router(visits_router)
app.include_router(heartbeat_router)
app.include_router(access_router)
app.include_router(dashboard_router)


@app.get("/api/health")
def health(request: Request, db: Session = Depends(get_db)):
    """存活探针：Docker HEALTHCHECK 与前端解析页状态灯（数据就绪/数据异常）共用。

    为何公开：探针必须在未登录时也可用，且只读、无副作用、不返回任何用户数据；
    公开端点按 S5 挂限流（30 次/分钟/IP），防止被刷成免费探测口。

    响应语义只走 HTTP 状态码（2026-09-18 爬虫复测收敛）：200 = 进程与数据库均
    可用，503 = 库不可用；body 不再携带 database 等内部状态字段——前端两处消费
    方（ParseHome 状态灯 / Dashboard 延迟测量）都只看请求成败，Docker
    HEALTHCHECK 只看状态码，去掉字段零影响，而外部探测者少得一份内态信息。
    """
    retry = health_limiter.allow(f"health:{rate_limit_key(request)}")
    if retry:
        raise HTTPException(status_code=429, detail="健康检查请求过于频繁")
    try:
        db.execute(text("SELECT 1"))  # 常量探测，无用户输入，无需绑定参数
    except Exception as exc:  # noqa: BLE001 — 探测失败本身就是要上报的状态
        logger.exception("健康检查探测数据库失败")
        raise HTTPException(status_code=503, detail="数据库暂不可用") from exc
    return {"status": "ok"}


# 静态目录：默认 backend/static，可用环境变量 VIDEOHUB_STATIC_DIR 覆盖（部署 / 测试用）。
# 必须在 import 期确定：下方“条件注册 + SPA 回退”都基于该目录判断。
_static_override = os.environ.get("VIDEOHUB_STATIC_DIR", "").strip()
STATIC_DIR = (
    Path(_static_override).resolve()
    if _static_override
    else Path(__file__).resolve().parent.parent / "static"
)

if (STATIC_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    # 爬虫知名文件：缺位时明确 404，不吐 SPA 空壳——200+HTML 会让爬虫把
    # sitemap.xml 当页面反复抓取空转（2026-09-18 爬虫复测发现项）。robots.txt
    # 是真实文件（frontend/public/robots.txt 经构建落此目录），走下方正常分支返回
    _CRAWLER_WELL_KNOWN = ("robots.txt", "sitemap.xml")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not Found")
        file = (STATIC_DIR / full_path).resolve()
        if full_path and file.is_file() and file.is_relative_to(STATIC_DIR):
            return FileResponse(file)
        if full_path in _CRAWLER_WELL_KNOWN:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(STATIC_DIR / "index.html")
