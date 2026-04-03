from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AppUserPreferences(Base):
    __tablename__ = "app_user_preferences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    daily_summary_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reminder_notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    calendar_export_default_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("AppUser", back_populates="preferences")
