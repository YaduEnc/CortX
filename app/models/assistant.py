from datetime import datetime, timezone
from enum import Enum
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AIExtractionStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"


class AIItemType(str, Enum):
    task = "task"
    reminder = "reminder"
    plan_step = "plan_step"


class AIItemStatus(str, Enum):
    open = "open"
    done = "done"
    dismissed = "dismissed"
    snoozed = "snoozed"


class AIExtraction(Base):
    __tablename__ = "ai_extractions"
    __table_args__ = (
        Index("ix_ai_extractions_user_status", "user_id", "status"),
        Index("ix_ai_extractions_session", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("capture_sessions.id", ondelete="CASCADE"), nullable=False)
    transcript_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    status: Mapped[str] = mapped_column(String(32), default=AIExtractionStatus.queued.value, nullable=False)
    intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("AppUser", back_populates="ai_extractions")
    session = relationship("CaptureSession", back_populates="ai_extraction")
    transcript = relationship("Transcript", back_populates="ai_extraction")
    items = relationship("AIItem", back_populates="extraction", cascade="all, delete-orphan")


class AIItem(Base):
    __tablename__ = "ai_items"
    __table_args__ = (
        Index("ix_ai_items_user_type_status", "user_id", "item_type", "status"),
        Index("ix_ai_items_extraction", "extraction_id"),
        Index("ix_ai_items_due", "due_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    extraction_id: Mapped[str] = mapped_column(String(36), ForeignKey("ai_extractions.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("capture_sessions.id", ondelete="CASCADE"), nullable=False)
    transcript_id: Mapped[str] = mapped_column(String(36), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False)

    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=AIItemStatus.open.value, nullable=False)
    source_segment_start_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_segment_end_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    extraction = relationship("AIExtraction", back_populates="items")
    user = relationship("AppUser")
    session = relationship("CaptureSession")
    transcript = relationship("Transcript")
