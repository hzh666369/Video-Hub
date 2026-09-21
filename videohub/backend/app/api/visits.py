from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import AccessLog, User
from app.services.access_log import record_access, today_start
from app.services.client_ip import get_client_ip
from app.services.ratelimit import visit_limiter

router = APIRouter(prefix="/api", tags=["visits"])

# 访问类活动口径：与数据看板/访问记录页一致（visit/login/register 都算「使用过平台」）
VISIT_ACTIONS = ("visit", "login", "register")


def _activity_count(db: Session, start=None) -> int:
    """访问类活动事件数；start 缺省为全量累计。"""
    conds = [AccessLog.action.in_(VISIT_ACTIONS)]
    if start is not None:
        conds.append(AccessLog.created_at >= start)
    return db.scalar(select(func.count()).select_from(AccessLog).where(*conds)) or 0


@router.post("/visits")
def record_visit(request: Request, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """打开解析页即计一次访问。数字只回馈给管理员，普通用户计数生效但拿不到值。

    口径（2026-09-15 统一）：今日/累计 = AccessLog 中 visit+login+register 活动数，
    与数据看板 KPI/趋势图同源同口径。不再维护 settings 的 visit_today/visit_total
    计数器——旧计数器只计 POST /visits（不含登录/注册），与看板口径不一致会导致
    两页「今日访问」数字对不上；历史计数器行留在库里不再读写。
    """
    # 每次调用写一条日志，按用户限流防高频刷库拖垮 SQLite
    retry = visit_limiter.allow(f"visit:{user.id}")
    if retry:
        raise HTTPException(status_code=429, detail="访问上报过于频繁")
    ip = get_client_ip(request)
    record_access(db, user, "visit", detail="解析首页", ip=ip, commit=False)
    db.commit()
    if user.is_admin:
        # 今日按服务器本地日期跨天归零（today_start），历史累计为全量活动数
        return {"today": _activity_count(db, today_start()), "total": _activity_count(db)}
    return {"today": None, "total": None}
