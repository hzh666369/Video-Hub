from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AccessLog(Base):
    __tablename__ = "access_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 用户被删除后日志仍需可读，故冗余存一份用户名快照（用户名注册后不可改，快照始终准确）
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    # 动作类型：visit=页面访问 / login=登录 / register=注册 / parse=解析视频
    action: Mapped[str] = mapped_column(String(16), index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # SQLite 的 CURRENT_TIMESTAMP 是 UTC，ORM 侧默认本地时间与看板「今天/昨天」本地边界一致
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "action": self.action,
            "detail": self.detail,
            "ip": self.ip,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
