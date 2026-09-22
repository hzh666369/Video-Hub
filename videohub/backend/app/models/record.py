from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Caption(Base):
    __tablename__ = "captions"

    record_id: Mapped[int] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), primary_key=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    srt_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    formatted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Record(Base):
    __tablename__ = "records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(16), default="single")  # single/homepage/vip
    parse_status: Mapped[str] = mapped_column(String(16), default="parsed")  # parsed/link_only
    platform: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    source_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # VIP 记录最近一次使用的解析线路名（settings.vip_routes 里的 name），切换线路时更新
    route_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_atlas: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # SQLite 的 CURRENT_TIMESTAMP 是 UTC，ORM 侧默认本地时间与看板「今天/昨天」本地边界一致；
    # 看板按 created_at 窗口统计，建索引（存量库由 main._ensure_columns 幂等补建）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), index=True)

    caption: Mapped[Caption | None] = relationship(
        Caption, uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_type": self.source_type,
            "parse_status": self.parse_status,
            "platform": self.platform,
            "source_url": self.source_url,
            "title": self.title,
            "cover_url": self.cover_url,
            "video_url": self.video_url,
            "route_name": self.route_name,
            "image_atlas": self.image_atlas or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "captions": None
            if self.caption is None
            else {
                "text_content": self.caption.text_content,
                "srt_content": self.caption.srt_content,
                "formatted_text": self.caption.formatted_text,
                "duration_minutes": self.caption.duration_minutes,
            },
        }
