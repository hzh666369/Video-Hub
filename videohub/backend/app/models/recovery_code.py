from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RecoveryCode(Base):
    """TOTP 两步验证的一次性恢复代码：只存加盐 SHA-256，用后即标记（S19）。

    用户删除/注销时靠 FK ON DELETE CASCADE 联动清理（对齐 captions 模式）。
    """

    __tablename__ = "recovery_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    # 单次使用：消费后置 True，登录时只匹配未用过的
    used: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
