"""管理员数据看板聚合端点：一次返回 KPI / 趋势 / 平台占比 / 排行 / 最新动态 / 系统状态。

只读、无用户输入参数；挂 require_perm("dashboard") + 宽松限流（S5，前端 60s 轮询）。
统计口径与 app/api/access.py 一致。所有指标均为真实统计：
  · 解析类口径（2026-09-15 统一）：「今日/累计解析」「趋势图解析量」「用户排行」一律取
    AccessLog 的 parse 动作数（解析操作次数，单调递增，用户删记录不影响）；
    「解析记录存量」(total_records) 与「平台占比」取 Record 表当前行数（用户删除
    记录会使存量下降）。两个口径在看板上分别标注，禁止互相混用。
  · 访问类口径（2026-09-15 统一）：今日/累计访问与趋势图一律取 AccessLog 的
    visit+login+register 活动数（旧 settings.visit_total 计数器只计打开解析页，
    与趋势口径不一致，已废弃不再读取）。
  · online_users —— 近 120 秒有心跳上报的去重登录用户数（实时在线口径，
    数据源 app/services/presence.py 内存心跳表，前端 30s 打一次）
  · system.*     —— 数据库探针延迟 / 进程运行时长 / 事件速率 / 库文件体积等实测值
  · delta_pct    —— 今日 vs 昨日同比；昨日无基线时按约定取值（今日>0 → +100 从无到有，
                    今日=0 → 0），保证前端始终能渲染涨跌方向，不再出现 null
"""
import time
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.deps import require_perm
from app.database import get_db
from app.models import AccessLog, Caption, Record, User
from app.services import presence
from app.services.ratelimit import dashboard_limiter

router = APIRouter(prefix="/api/admin", tags=["dashboard"])

VISIT_ACTIONS = ("visit", "login", "register")
TREND_DAYS = 90
# 平台占比直接按前端展示口径返回：总量降序取前 5 + 其余合并 other（合并段涨跌
# 先把今日/昨日窗口计数求和再算）。前端不再二次合并——前端没有窗口计数，
# 只能对百分比做加法，数学上不成立
PLATFORM_TOP = 5
TOP_USERS = 5
RECENT_LIMIT = 20
# 在线窗口：前端 30s 打一次心跳（后台标签页被浏览器节流到 ~60s），120s 窗口
# 前台漏 3 次、后台漏 1 次都不会误判掉线
ONLINE_WINDOW_SEC = 120

# 进程内单调时钟起点：模块随 worker 加载时记录，用作服务运行时长的近似基准
_STARTED_MONOTONIC = time.monotonic()


def _pct_delta(today: int, yesterday: int) -> float:
    """今日 vs 昨日涨跌百分比。
    口径约定（2026-09-15）：昨日为 0（无基线）时不再返回 null —— 今日 >0 记为 +100
    （从无到有）、今日 =0 记为 0。涨跌是列表必渲染列，null 会让前端只能显示「—」。
    """
    if not yesterday:
        return 100.0 if today else 0.0
    return round((today - yesterday) / yesterday * 100, 1)


@router.get("/dashboard")
def dashboard(request: Request, user: User = Depends(require_perm("dashboard")), db: Session = Depends(get_db)):
    """管理员数据看板全量数据。为何挂限流：聚合查询略重，防异常循环刷库。"""
    retry = dashboard_limiter.allow(f"dashboard:{user.id}")
    if retry:
        raise HTTPException(status_code=429, detail="看板刷新过于频繁，请稍后再试")

    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    trend_start_date = date.today() - timedelta(days=TREND_DAYS - 1)
    trend_start = datetime.combine(trend_start_date, datetime.min.time())

    def _log_count(actions: tuple[str, ...], start: datetime, end: datetime | None = None) -> int:
        conds = [AccessLog.action.in_(actions), AccessLog.created_at >= start]
        if end is not None:
            conds.append(AccessLog.created_at < end)
        return db.scalar(select(func.count()).select_from(AccessLog).where(*conds)) or 0

    def _log_total(actions: tuple[str, ...]) -> int:
        return db.scalar(
            select(func.count()).select_from(AccessLog).where(AccessLog.action.in_(actions))) or 0

    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    week_new_users = db.scalar(
        select(func.count()).select_from(User).where(User.created_at >= now - timedelta(days=7))) or 0

    kpis = {
        "today_visits": _log_count(VISIT_ACTIONS, today),
        "yesterday_visits": _log_count(VISIT_ACTIONS, yesterday, today),
        "today_parses": _log_count(("parse",), today),
        "yesterday_parses": _log_count(("parse",), yesterday, today),
        "total_users": total_users,
        "week_new_users": week_new_users,
        # 累计解析 = 历史解析操作总数（AccessLog parse 动作，单调递增，与今日/趋势同源）
        "total_parses": _log_total(("parse",)),
        # 解析记录存量 = Record 当前行数（用户删除记录会下降，仅 Storage 面板/平台占比用）
        "total_records": db.scalar(select(func.count()).select_from(Record)) or 0,
        # 累计访问 = 历史访问类活动总数（visit+login+register，与今日访问/趋势图同源同口径）
        "total_visits": _log_total(VISIT_ACTIONS),
    }

    # 在线人数：近 120 秒有心跳的登录用户（实时心跳口径，2026-09-15 起替代旧的
    # 「近 15 分钟 AccessLog 活动」推断——旧口径感知不到「挂着页面但没有动作」的
    # 在线用户，且会把已离开的用户多算 15 分钟；presence 为单进程内存表，重启清零后
    # 1-2 分钟内各客户端心跳回来即恢复）
    online_users = presence.online_count(ONLINE_WINDOW_SEC)

    # 近 90 天趋势：按本地日期分组（created_at 存本地时间），Python 侧补齐空缺日为 0
    rows = db.execute(
        select(func.date(AccessLog.created_at), AccessLog.action, func.count())
        .where(AccessLog.created_at >= trend_start,
               AccessLog.action.in_((*VISIT_ACTIONS, "parse")))
        .group_by(func.date(AccessLog.created_at), AccessLog.action)
    ).all()
    visits_map: dict[str, int] = {}
    parses_map: dict[str, int] = {}
    for day, action, n in rows:
        key = day if isinstance(day, str) else day.isoformat()
        # 访问量 = visit+login+register 三类动作之和：按 (日期,动作) 分组后必须累加，
        # 直接赋值会让同一天的后一类动作覆盖前一类，访问量被低估（2026-09-15 复核修复）
        if action in VISIT_ACTIONS:
            visits_map[key] = visits_map.get(key, 0) + n
        else:
            parses_map[key] = parses_map.get(key, 0) + n
    full_days = [trend_start_date + timedelta(days=i) for i in range(TREND_DAYS)]
    trend = {
        "days": [d.strftime("%m-%d") for d in full_days],
        "visits": [visits_map.get(d.isoformat(), 0) for d in full_days],
        "parses": [parses_map.get(d.isoformat(), 0) for d in full_days],
    }

    # 平台占比：总量降序取前 6，其余合并 other；涨跌按「今日新增记录 vs 昨日新增记录」
    # 计算（合并段先把窗口计数求和再算涨跌，不能拿单平台值代替）
    platform_rows = db.execute(
        select(Record.platform, func.count())
        .group_by(Record.platform).order_by(func.count().desc(), Record.platform)
    ).all()

    def _record_window_counts(start: datetime, end: datetime | None = None) -> dict[str, int]:
        conds = [Record.created_at >= start]
        if end is not None:
            conds.append(Record.created_at < end)
        return dict(db.execute(
            select(Record.platform, func.count()).where(*conds).group_by(Record.platform)).all())

    rec_today = _record_window_counts(today)
    rec_yesterday = _record_window_counts(yesterday, today)

    platforms: list[dict] = []
    other_count = 0
    other_today = 0
    other_yesterday = 0
    for i, (platform, n) in enumerate(platform_rows):
        if i < PLATFORM_TOP:
            platforms.append({
                "platform": platform,
                "count": n,
                "delta_pct": _pct_delta(rec_today.get(platform, 0), rec_yesterday.get(platform, 0)),
            })
        else:
            other_count += n
            other_today += rec_today.get(platform, 0)
            other_yesterday += rec_yesterday.get(platform, 0)
    if other_count:
        platforms.append({
            "platform": "other",
            "count": other_count,
            "delta_pct": _pct_delta(other_today, other_yesterday),
        })

    # 解析次数 TOP5（联 users 取名；用户删除时 user_id 已置空，join 天然排除）
    top_rows = db.execute(
        select(User.id, User.username, func.count())
        .join(AccessLog, AccessLog.user_id == User.id)
        .where(AccessLog.action == "parse")
        .group_by(User.id).order_by(func.count().desc(), User.username)
        .limit(TOP_USERS)
    ).all()

    def _parse_window_counts(start: datetime, end: datetime | None = None) -> dict[int, int]:
        conds = [AccessLog.action == "parse", AccessLog.created_at >= start]
        if end is not None:
            conds.append(AccessLog.created_at < end)
        return dict(db.execute(
            select(AccessLog.user_id, func.count()).where(*conds).group_by(AccessLog.user_id)).all())

    parse_today = _parse_window_counts(today)
    parse_yesterday = _parse_window_counts(yesterday, today)
    top_users = [
        {
            "user_id": uid,
            "username": name,
            "parse_count": n,
            "delta_pct": _pct_delta(parse_today.get(uid, 0), parse_yesterday.get(uid, 0)),
        }
        for uid, name, n in top_rows
    ]

    recent_logs = db.scalars(
        select(AccessLog)
        .order_by(AccessLog.created_at.desc(), AccessLog.id.desc())
        .limit(RECENT_LIMIT)
    ).all()

    # ---- 系统状态（全部真实测量值，展示口径见前端 DashStatus） ----
    t0 = time.perf_counter()
    db.execute(text("SELECT 1"))
    db_latency_ms = round((time.perf_counter() - t0) * 1000, 1)

    # 事件速率：近 60 秒的访问类+解析类活动数。显式动作白名单 —— 与前端 DashStatus
    # 注释的口径承诺一致，未来新增动作类型（心跳/导出等）不会静默混入该指标
    events_per_min = _log_count((*VISIT_ACTIONS, "parse"), now - timedelta(seconds=60))
    today_events = _log_count((*VISIT_ACTIONS, "parse"), today)
    week_parses = _log_count(("parse",), now - timedelta(days=7))
    captions = db.scalar(select(func.count()).select_from(Caption)) or 0

    def _db_size_mb() -> float | None:
        """SQLite 库文件体积（MB）；非 SQLite 后端返回 None，前端该列不渲染。"""
        try:
            if db.bind is None or db.bind.dialect.name != "sqlite":
                return None
            page_count = db.execute(text("PRAGMA page_count")).scalar() or 0
            page_size = db.execute(text("PRAGMA page_size")).scalar() or 0
            return round(page_count * page_size / (1024 * 1024), 1)
        except Exception:  # noqa: BLE001 — 状态面板是旁路信息，取不到体积不应拖垮看板
            return None

    system = {
        "db_latency_ms": db_latency_ms,
        "uptime_minutes": int((time.monotonic() - _STARTED_MONOTONIC) / 60),
        "events_per_min": events_per_min,
        "today_events": today_events,
        "week_parses": week_parses,
        "captions": captions,
        "db_size_mb": _db_size_mb(),
        # 是否经 Cloudflare 隧道到达：只判头存在性（不信任其值做身份/风控判定，身份口径仍走 S1）
        "via_tunnel": bool(request.headers.get("cf-connecting-ip") or request.headers.get("cf-ray")),
    }

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "online_users": online_users,
        "kpis": kpis,
        "trend": trend,
        "platforms": platforms,
        "top_users": top_users,
        "recent": [log.to_dict() for log in recent_logs],
        "system": system,
    }
