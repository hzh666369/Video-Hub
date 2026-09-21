from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models import Record, User
from app.services.settings import get_setting, get_vip_routes, is_https_prefix
from app.services.urlguard import ForbiddenUpstreamError, validate_proxy_target

router = APIRouter(prefix="/api/records", tags=["records"])


@router.get("")
def list_records(platform: str | None = None, source_type: str | None = None,
                 q: str | None = None,
                 page: int = Query(1, ge=1),
                 page_size: int = Query(20, ge=1, le=100),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # selectinload 预取 caption：to_dict 会访问关系属性，逐条懒加载是 N+1
    #（page_size=20 时 21 条 SQL → 2 条）
    stmt = select(Record).options(selectinload(Record.caption)).where(Record.user_id == user.id)
    if platform:
        stmt = stmt.where(Record.platform == platform)
    if source_type:
        stmt = stmt.where(Record.source_type == source_type)
    if q:
        stmt = stmt.where(Record.title.contains(q))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(Record.created_at.desc(), Record.id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [r.to_dict() for r in items], "total": total,
            "page": page, "page_size": page_size}


def _get_own_record(record_id: int, user: User, db: Session) -> Record:
    rec = db.get(Record, record_id)
    if rec is None or rec.user_id != user.id:
        raise HTTPException(status_code=404, detail="记录不存在")
    return rec


@router.get("/{record_id}")
def get_record(record_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_own_record(record_id, user, db).to_dict()


@router.delete("/{record_id}")
def delete_record(record_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_get_own_record(record_id, user, db))
    db.commit()
    return {"ok": True}


class BatchDeleteIn(BaseModel):
    ids: list[int]


@router.post("/batch-delete")
def batch_delete_records(body: BatchDeleteIn,
                         user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 去重保持顺序；只删除属于当前用户的记录，不存在/他人的 ID 静默忽略
    ids = list(dict.fromkeys(body.ids))
    if not ids:
        raise HTTPException(status_code=400, detail="未选择任何记录")
    if len(ids) > 200:
        raise HTTPException(status_code=400, detail="单次最多删除 200 条")
    records = db.scalars(
        select(Record).where(Record.user_id == user.id, Record.id.in_(ids))
    ).all()
    for rec in records:
        db.delete(rec)
    db.commit()
    return {"ok": True, "deleted": len(records)}


class TitleUpdateIn(BaseModel):
    title: str


@router.patch("/{record_id}")
def update_title(record_id: int, body: TitleUpdateIn,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rec = _get_own_record(record_id, user, db)
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    if len(title) > 100:
        raise HTTPException(status_code=400, detail="标题最长 100 个字符")
    # 同一账号内标题唯一（大小写不敏感），排除当前记录自身
    dup = db.scalar(
        select(Record).where(
            Record.user_id == user.id,
            Record.id != record_id,
            func.lower(Record.title) == title.lower(),
        )
    )
    if dup:
        raise HTTPException(status_code=409, detail="已存在同名视频，请换个标题")
    rec.title = title
    db.commit()
    return rec.to_dict()


def _resolve_vip_route(rec: Record, route_param: str | None, db: Session) -> dict:
    """线路优先级：?route= 切换参数 > 记录上次用的线路 > 管理员默认线路 > 第一条。"""
    routes = get_vip_routes(db)
    if route_param is not None and not any(r["name"] == route_param for r in routes):
        raise HTTPException(status_code=400, detail="未知线路")
    name = route_param or rec.route_name or get_setting(db, "vip_default_route")
    route = next((r for r in routes if r["name"] == name), routes[0] if routes else None)
    if route is None:
        raise HTTPException(status_code=400, detail="尚无可用解析线路")
    # 入库校验是防线一，这里再挡一次：历史脏数据/直改库的 javascript: prefix
    # 会原样绑到播放页 iframe（存储型 XSS），使用时必须复验
    if not is_https_prefix(route.get("prefix")):
        raise HTTPException(status_code=400, detail="线路配置非法：prefix 必须以 https:// 开头，请管理员在设置中修正")
    return route


@router.get("/{record_id}/embed")
def record_embed(record_id: int, route: str | None = None,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rec = _get_own_record(record_id, user, db)
    if rec.source_type != "vip":
        raise HTTPException(status_code=400, detail="非 VIP 记录")
    chosen = _resolve_vip_route(rec, route, db)
    # 显式切换线路时写回记录：下次打开沿用，也供列表展示
    if route and rec.route_name != chosen["name"]:
        rec.route_name = chosen["name"]
        db.commit()
    return {"embed_url": chosen["prefix"] + quote(rec.video_url, safe=""),
            "route_name": chosen["name"]}


@router.get("/{record_id}/embed-check")
async def record_embed_check(record_id: int, route: str | None = None,
                             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """后台探测线路是否允许 iframe 内嵌；与 /embed 分离，避免阻塞播放器加载。"""
    rec = _get_own_record(record_id, user, db)
    if rec.source_type != "vip":
        raise HTTPException(status_code=400, detail="非 VIP 记录")
    chosen = _resolve_vip_route(rec, route, db)
    target = chosen["prefix"] + quote(rec.video_url, safe="")
    # 服务器端 HEAD 探测 = 出站请求，与流式代理同口径过 SSRF 校验：
    # 被盗的管理员会话若把线路指到内网地址，不得借此探测内网
    try:
        await validate_proxy_target(target)
    except ForbiddenUpstreamError:
        raise HTTPException(status_code=403, detail="该线路指向受限地址，已拒绝探测") from None
    embeddable = None
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            resp = await client.head(target)
        xfo = resp.headers.get("x-frame-options", "").lower()
        embeddable = not ("deny" in xfo or "sameorigin" in xfo)
    except httpx.HTTPError:
        embeddable = None
    return {"route_name": chosen["name"], "embeddable": embeddable}
