from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

# 会话密码版本指纹长度：取 bcrypt hash 尾部若干位（含随机盐+摘要，碰撞可忽略）。
# 登录/注册时写入 session，改密码后指纹变化 → 旧会话全部失效（含被盗号的旧会话）。
PW_FINGERPRINT_LEN = 12


def password_fingerprint(password_hash: str) -> str:
    return password_hash[-PW_FINGERPRINT_LEN:]


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    if request.session.get("pw_pv") != password_fingerprint(user.password_hash):
        # 密码已在别处被修改（本人改密或管理员重置），当前会话立即下线
        request.session.clear()
        raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def require_perm(code: str):
    """功能点只读授权依赖(S4 扩展):管理员恒真;普通用户须被授予该权限码。

    用法:Depends(require_perm("dashboard"))。授权=只读可见,
    写操作端点仍必须挂 require_admin(设计见 spec 2.4 语义边界)。
    """
    def dep(user: User = Depends(get_current_user)) -> User:
        if not user.has_perm(code):
            raise HTTPException(status_code=403, detail="没有访问该功能的权限")
        return user
    return dep
