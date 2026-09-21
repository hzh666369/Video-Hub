import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # 新手引导是否已完成：注册后为 False，完成引导或跳过后置 True（可由前端再次唤起而不改此标记）
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # 细粒度功能点授权(JSON 数组串,如 '["dashboard","access"]'):授权=只读可见,
    # 写操作仍限管理员;管理员 has_perm 恒真,本列对其无意义。默认 "[]" 与旧版行为一致
    permissions: Mapped[str] = mapped_column(String(255), default="[]", server_default="[]")
    # TOTP 两步验证（S19）：secret 仅在 DB 存储、绝不写日志/接口回传（setup 时回传一次
    # 除外）；enabled 置位前 secret 只算"待确认"；last_step 单调记录已消费的时间步，
    # 拒绝同一验证码重放
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True,
                                                    default=None, server_default=None)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    totp_last_step: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # SQLite 的 CURRENT_TIMESTAMP 是 UTC，ORM 侧默认本地时间与看板「今天/昨天」本地边界一致
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())

    def __init__(self, **kwargs: object) -> None:
        # 列级 default 只在 flush/INSERT 时生效;契约要求瞬态(未入库)对象默认即为 "[]",
        # 故构造期补一次 setdefault(显式传 None 不覆盖,由 permission_set 容错)
        kwargs.setdefault("permissions", "[]")
        super().__init__(**kwargs)

    @property
    def permission_set(self) -> set[str]:
        """permissions JSON 串 → 字符串集合;空值/坏 JSON/非字符串成员一律容错降级。"""
        try:
            data = json.loads(self.permissions or "[]")
        except (TypeError, ValueError):
            return set()
        if not isinstance(data, list):
            return set()
        return {item for item in data if isinstance(item, str)}

    def has_perm(self, code: str) -> bool:
        """功能点授权判定:管理员恒真;普通用户看 permissions 集合。"""
        return self.is_admin or code in self.permission_set
