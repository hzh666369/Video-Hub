from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import Record, User
from app.services.access_log import record_access
from app.services.client_ip import get_client_ip
from app.services.platform import detect
from app.services.ratelimit import parse_daily_limiter, parse_limiter
from app.services.settings import get_setting, get_vip_routes, is_https_prefix

router = APIRouter(prefix="/api/parse", tags=["parse"])

# URL 入参长度上限：超长串只消耗内存与日志空间，2048 已覆盖所有正常平台链接
MAX_URL_LENGTH = 2048


class DetectIn(BaseModel):
    url: str = Field(max_length=MAX_URL_LENGTH)


@router.post("/detect")
def detect_url(body: DetectIn, _: User = Depends(get_current_user)):
    d = detect(body.url)
    return {"kind": d.kind, "platform": d.platform, "is_homepage": d.is_homepage}


class VipIn(BaseModel):
    url: str = Field(max_length=MAX_URL_LENGTH)
    route_name: str | None = None


@router.get("/vip-routes")
def vip_routes(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    routes = get_vip_routes(db)
    default_route = get_setting(db, "vip_default_route") or (routes[0]["name"] if routes else None)
    return {"routes": routes, "default_route": default_route}


def _build_embed_url(prefix: str, url: str) -> str:
    return prefix + quote(url, safe="")


@router.post("/vip")
def parse_vip(body: VipIn, request: Request, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    # 写库端点按用户分桶限流（S5）：与 /visits 同口径，公开注册场景下防脚本化刷库
    # 拖垮 SQLite 单写者（每次调用写 Record + AccessLog 两行，2026-09-15 审计 M-4）
    retry = parse_limiter.allow(f"parse:{user.id}")
    if retry:
        raise HTTPException(status_code=429, detail="解析请求过于频繁，请稍后再试")
    # 每日配额（2026-09-18 爬虫视角安全测试报告建议 5）：分钟级限流管不住低速率
    # 长跑，登录账号仍可被当作免费解析 API 用（写库 + VIP 线路消耗）；滚动 24h
    # 300 次/用户，脚本化农场约 10 分钟烧完全天配额，正常追剧用户不受影响
    retry = parse_daily_limiter.allow(f"parse:{user.id}")
    if retry:
        raise HTTPException(
            status_code=429,
            detail=f"解析次数已达每日上限，请约 {int(retry // 3600) + 1} 小时后再试")
    d = detect(body.url)
    if d.kind != "vip":
        raise HTTPException(status_code=400, detail="无法识别为长视频平台链接")
    routes = get_vip_routes(db)
    route_name = body.route_name or get_setting(db, "vip_default_route")
    route = next((r for r in routes if r["name"] == route_name), routes[0] if routes else None)
    if route is None:
        raise HTTPException(status_code=400, detail="尚无可用解析线路，请管理员在设置中添加")
    # 与 records._resolve_vip_route 同口径：防历史脏数据/直改库的 javascript: prefix 进 iframe
    if not is_https_prefix(route.get("prefix")):
        raise HTTPException(status_code=400, detail="线路配置非法：prefix 必须以 https:// 开头，请管理员在设置中修正")
    # 判重：24h 内同用户同链接复用既有记录——刷新重试/多标签重复提交不再堆重复行。
    # ⚠️ 红线 3.1 的显式豁免（已登记 docs/SECURITY.md §3.1）：判重窗口是**滑动 24h**，
    # SQLite 无法用 (user_id, source_url) 唯一索引表达「只在 24h 内唯一」，因此这里
    # **无法**配 DB 唯一约束兜底。最坏后果仅是并发下同一链接多插一行重复记录，不涉及
    # 越权、越户或数据损坏；且每次调用已由 parse_limiter 封住频率上界。
    rec = db.scalar(
        select(Record).where(
            Record.user_id == user.id,
            Record.source_url == body.url,
            Record.created_at >= datetime.now() - timedelta(hours=24),
        ).order_by(Record.created_at.desc()).limit(1))
    if rec is None:
        rec = Record(user_id=user.id, source_type="vip", parse_status="parsed",
                     platform=d.platform, source_url=body.url, video_url=body.url,
                     route_name=route["name"])
        db.add(rec)
    elif body.route_name and rec.route_name != route["name"]:
        # 显式换线路时同步记录，与 /embed 的切换写回口径一致
        rec.route_name = route["name"]
    ip = get_client_ip(request)
    record_access(db, user, "parse", detail=f"{d.platform} | {body.url}", ip=ip, commit=False)
    db.commit()
    return {"record": rec.to_dict(), "embed_url": _build_embed_url(route["prefix"], body.url)}
