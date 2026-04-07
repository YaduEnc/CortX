from datetime import datetime, timezone
from enum import Enum
import uuid

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MemoryLinkType(str, Enum):
    person = "person"
    project = "project"
    place = "place"
    founder_idea = "founder_idea"


class MemoryLinkSource(str, Enum):
    ai_suggested = "ai_suggested"
    manual = "manual"
    manual_created = "manual_created"


class MemoryLinkStatus(str, Enum):
    suggested = "suggested"
    confirmed = "confirmed"
    rejected = "rejected"


class MemoryLink(Base):
    __tablename__ = "memory_links"
    __table_args__ = (
        UniqueConstraint("session_id", "entity_id", "link_type", name="uq_memory_links_session_entity_type"),
        UniqueConstraint("session_id", "founder_idea_id", "link_type", name="uq_memory_links_session_founder_type"),
        CheckConstraint(
            "((entity_id IS NOT NULL AND founder_idea_id IS NULL) OR (entity_id IS NULL AND founder_idea_id IS NOT NULL))",
            name="ck_memory_links_single_target",
        ),
        Index("ix_memory_links_user_session_status", "user_id", "session_id", "status"),
        Index("ix_memory_links_entity", "entity_id"),
        Index("ix_memory_links_founder", "founder_idea_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("capture_sessions.id", ondelete="CASCADE"), nullable=False)
    link_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("entities.id", ondelete="CASCADE"), nullable=True)
    founder_idea_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("founder_idea_clusters.id", ondelete="CASCADE"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=MemoryLinkStatus.suggested.value)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    session = relationship("CaptureSession")
    entity = relationship("Entity")
    founder_idea = relationship("FounderIdeaCluster")
    user = relationship("AppUser", back_populates="memory_links")
