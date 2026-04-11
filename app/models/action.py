from datetime import datetime, timezone
from enum import Enum
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PendingActionType(str, Enum):
    sms = "sms"
    whatsapp = "whatsapp"
    email = "email"
    iMessage = "iMessage"


class PendingActionStatus(str, Enum):
    pending = "pending"
    sent = "sent"
    dismissed = "dismissed"
    edited_sent = "edited_sent"


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        Index("idx_contacts_user_id", "user_id"),
        Index("idx_contacts_name_search", "name_aliases", postgresql_using="gin"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    whatsapp_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("AppUser", back_populates="contacts")
    pending_actions = relationship("PendingAction", back_populates="contact")


class PendingAction(Base):
    __tablename__ = "pending_actions"
    __table_args__ = (
        Index("idx_pending_actions_user_id", "user_id"),
        Index("idx_pending_actions_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("capture_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )

    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=PendingActionStatus.pending.value, nullable=False)

    contact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    recipient_name: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipient_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    draft_subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_body: Mapped[str] = mapped_column(Text, nullable=False)
    original_transcript_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("AppUser", back_populates="pending_actions")
    session = relationship("CaptureSession", back_populates="pending_actions")
    contact = relationship("Contact", back_populates="pending_actions")
