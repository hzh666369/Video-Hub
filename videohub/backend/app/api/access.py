from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_perm
from app.database import get_db
from app.models import AccessLog, User
from app.services.access_log import today_start

router = APIRouter(prefix="/api/admin/access", tags=["access"])


@router.get("/summary")
def access_summary(_: User = Depends(require_perm("access")), db: Session = Depends(get_db)):
    """全量用户的访问汇总：最近访问时间 / 今日访问 / 历史访问 / 解析个数。"""
    # 访问类动作（visit/login/register 都算「使用过平台」），解析单独统计
    visit_conds = AccessLog.action.in_(("visit", "login", "register"))

    total_rows = db.execute(
        select(AccessLog.user_id, func.count())
        .where(visit_conds).group_by(AccessLog.user_id)
    ).all()
    today_rows = db.execute(
        select(AccessLog.user_id, func.count())
        .where(visit_conds, AccessLog.created_at >= today_start()).group_by(AccessLog.user_id)
    ).all()
    parse_rows = db.execute(
        select(AccessLog.user_id, func.count())
        .where(AccessLog.action == "parse").group_by(AccessLog.user_id)
    ).all()
    last_rows = db.execute(
        select(AccessLog.user_id, func.max(AccessLog.created_at))
        .where(visit_conds).group_by(AccessLog.user_id)
    ).all()

    total = {uid: n for uid, n in total_rows if uid is not None}
    today = {uid: n for uid, n in today_rows if uid is not None}
    parse = {uid: n for uid, n in parse_rows if uid is not None}
    last = {uid: ts.isoformat() if ts else None for uid, ts in last_rows if uid is not None}

    items = []
    for u in db.scalars(select(User).order_by(User.id)).all():
        items.append({
            "user_id": u.id,
            "username": u.username,
            "is_admin": u.is_admin,
            "last_visit_at": last.get(u.id),
            "today_count": today.get(u.id, 0),
            "total_count": total.get(u.id, 0),
            "parse_count": parse.get(u.id, 0),
        })
    return {"items": items, "date": date.today().isoformat()}


@router.get("/logs")
def access_logs(
    user_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_perm("access")), db: Session = Depends(get_db),
):
    """访问明细（可按用户 / 动作过滤，倒序分页）。user_id 不传则返回全站明细。"""
    conds = []
    if user_id is not None:
        conds.append(AccessLog.user_id == user_id)
    if action:
        conds.append(AccessLog.action == action)

    where = list(conds)
    total = db.scalar(select(func.count()).select_from(AccessLog).where(*where)) or 0
    rows = db.scalars(
        select(AccessLog).where(*where)
        .order_by(AccessLog.created_at.desc(), AccessLog.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [r.to_dict() for r in rows]}
