from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import Record, User
from app.services.proxy import ProxyExpiredError, stream_response
from app.services.urlguard import ForbiddenUpstreamError, validate_proxy_target

router = APIRouter(prefix="/api/stream", tags=["stream"])


def _own_record(record_id: int, user: User, db: Session) -> Record:
    rec = db.get(Record, record_id)
    if rec is None or rec.user_id != user.id:
        raise HTTPException(status_code=404, detail="记录不存在")
    return rec


@router.get("/{record_id}")
async def stream_video(record_id: int, request: Request,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rec = _own_record(record_id, user, db)
    if rec.source_type == "vip":
        raise HTTPException(status_code=400, detail="VIP 记录不支持流式代理")
    if rec.parse_status != "parsed" or not rec.video_url:
        raise HTTPException(status_code=400, detail="该条目尚未解析")
    # 旧解析链路（已下线的 92k）留下的记录 URL 不受平台白名单约束，代理前必须校验目标
    try:
        await validate_proxy_target(rec.video_url)
    except ForbiddenUpstreamError:
        raise HTTPException(status_code=403, detail="该直链指向受限地址，已拒绝代理") from None
    try:
        return await stream_response(request, rec.video_url, rec.platform)
    except ProxyExpiredError:
        raise HTTPException(status_code=410, detail="视频直链已过期，请重新解析") from None


@router.get("/{record_id}/cover")
async def stream_cover(record_id: int, request: Request,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rec = _own_record(record_id, user, db)
    if not rec.cover_url:
        raise HTTPException(status_code=404, detail="无封面")
    try:
        await validate_proxy_target(rec.cover_url)
    except ForbiddenUpstreamError:
        raise HTTPException(status_code=403, detail="封面地址受限，已拒绝代理") from None
    try:
        return await stream_response(request, rec.cover_url, rec.platform)
    except ProxyExpiredError:
        raise HTTPException(status_code=404, detail="封面不可用") from None
