import secrets

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import persist_env, settings
from app.models import User

# bcrypt 只取密码前 72 字节，5.x 对超长输入直接抛 ValueError；
# 统一在入口校验前拦截，避免泄露成登录/注册接口的 500
MAX_PASSWORD_BYTES = 72


def _is_overlong(plain: str) -> bool:
    return len(plain.encode()) > MAX_PASSWORD_BYTES


def hash_password(plain: str) -> str:
    if _is_overlong(plain):
        raise ValueError(f"password exceeds {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    # 超长输入不可能匹配任何合法哈希（入库前已被上限拦住），按校验失败处理而非抛异常
    if _is_overlong(plain):
        return False
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def generate_password(length: int = 12) -> str:
    """字母+数字的可读随机密码，避免 0/O、1/l 这类易混淆字符。"""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def seed_admin(db: Session) -> str | None:
    """首启建管理员，返回生成的初始密码；已有账户时返回 None 不做任何改动。

    密码来源：环境变量 / .env 的 VIDEOHUB_ADMIN_PASSWORD；未配置则生成随机密码
    并写回 .env，杜绝 admin123 这类默认口令。
    """
    if db.scalar(select(func.count(User.id))):
        return None
    password = settings.admin_password or generate_password()
    if not settings.admin_password:
        persist_env("VIDEOHUB_ADMIN_PASSWORD", password)
    db.add(User(username="admin", password_hash=hash_password(password), is_admin=True,
                onboarding_completed=True))  # 管理员不需要新手引导
    db.commit()
    return password
