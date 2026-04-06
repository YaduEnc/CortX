from datetime import date, datetime, timezone
from enum import Enum
import uuid

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FounderIdeaStatus(str, Enum):
    emerging = "emerging"
    active = "active"
    validating = "validating"
    paused = "paused"
    dropped = "dropped"


class FounderIdeaMemoryRole(str, Enum):
    origin = "origin"
    evidence = "evidence"
    refinement = "refinement"
    contradiction = "contradiction"
    action = "action"


class FounderSignalType(str, Enum):
    pain_point = "pain_point"
    obsession = "obsession"
    contradiction = "contradiction"
    opportunity = "opportunity"
    market_signal = "market_signal"


class FounderIdeaActionStatus(str, Enum):
    open = "open"
    done = "done"
    dismissed = "dismissed"


class FounderIdeaCluster(Base):
    __tablename__ = "founder_idea_clusters"
    __table_args__ = (
        Index("ix_founder_idea_clusters_user_status", "user_id", "status"),
        Index("ix_founder_idea_clusters_user_last_seen", "user_id", "last_seen_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    problem_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_solution: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_user: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=FounderIdeaStatus.emerging.value, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    novelty_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    conviction_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    mention_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("AppUser", back_populates="founder_ideas")
    memories = relationship("FounderIdeaMemory", back_populates="idea_cluster", cascade="all, delete-orphan")
    actions = relationship("FounderIdeaAction", back_populates="idea_cluster", cascade="all, delete-orphan")
    signals = relationship("FounderSignal", back_populates="idea_cluster")


class FounderIdeaMemory(Base):
    __tablename__ = "founder_idea_memories"
    __table_args__ = (
        UniqueConstraint("idea_cluster_id", "session_id", name="uq_founder_idea_memory_session"),
        Index("ix_founder_idea_memories_session", "session_id"),
        Index("ix_founder_idea_memories_idea", "idea_cluster_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idea_cluster_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("founder_idea_clusters.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("capture_sessions.id", ondelete="CASCADE"), nullable=False)
    transcript_id: Mapped[str] = mapped_column(String(36), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    role: Mapped[str] = mapped_column(String(32), default=FounderIdeaMemoryRole.evidence.value, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    idea_cluster = relationship("FounderIdeaCluster", back_populates="memories")
    session = relationship("CaptureSession")
    transcript = relationship("Transcript")


class FounderIdeaAction(Base):
    __tablename__ = "founder_idea_actions"
    __table_args__ = (
        Index("ix_founder_idea_actions_user_status", "user_id", "status"),
        Index("ix_founder_idea_actions_idea", "idea_cluster_id"),
        Index("ix_founder_idea_actions_due", "due_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idea_cluster_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("founder_idea_clusters.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=FounderIdeaActionStatus.open.value, nullable=False)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    idea_cluster = relationship("FounderIdeaCluster", back_populates="actions")


class FounderSignal(Base):
    __tablename__ = "founder_signals"
    __table_args__ = (
        Index("ix_founder_signals_user_type_created", "user_id", "signal_type", "created_at"),
        Index("ix_founder_signals_idea", "idea_cluster_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    idea_cluster_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("founder_idea_clusters.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("capture_sessions.id", ondelete="CASCADE"), nullable=True)
    transcript_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=True)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    idea_cluster = relationship("FounderIdeaCluster", back_populates="signals")
    session = relationship("CaptureSession")
    transcript = relationship("Transcript")


class WeeklyFounderMemo(Base):
    __tablename__ = "weekly_founder_memos"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_weekly_founder_memo_user_week"),
        Index("ix_weekly_founder_memos_user_week", "user_id", "week_start"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    memo_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    top_ideas_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    top_risks_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    top_actions_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("AppUser", back_populates="weekly_founder_memos")
