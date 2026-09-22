"""在线心跳端点：登录用户周期性上报「我还活着」，供看板实时在线人数统计。

只写内存 presence 表：不落库、不写访问日志，无副作用外溢；POST 动词（GET 禁副作用红线）；
挂 get_current_user（S4）+ 按用户限流（S5，防异常客户端高频空调用）。
"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models import User
from app.services import presence
from app.services.ratelimit import heartbeat_limiter

router = APIRouter(prefix="/api", tags=["heartbeat"])


@router.post("/heartbeat")
def heartbeat(user: User = Depends(get_current_user)):
    """记录一次心跳。前端 30s 打一次（切回前台补打），看板按 120s 窗口数在线。"""
    retry = heartbeat_limiter.allow(f"heartbeat:{user.id}")
    if retry:
        raise HTTPException(status_code=429, detail="心跳上报过于频繁")
    presence.beat(user.id)
    return {"ok": True}
