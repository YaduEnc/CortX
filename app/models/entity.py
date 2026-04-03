from datetime import datetime, timezone
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EntityType:
    PERSON = "person"
    PROJECT = "project"
    TOPIC = "topic"
    PLACE = "place"
    ORGANIZATION = "organization"


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (
        Index("ix_entities_user_type", "user_id", "entity_type"),
        Index("ix_entities_user_name", "user_id", "normalized_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    mention_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    mentions = relationship("EntityMention", back_populates="entity", cascade="all, delete-orphan")


class EntityMention(Base):
    __tablename__ = "entity_mentions"
    __table_args__ = (
        Index("ix_entity_mentions_entity", "entity_id"),
        Index("ix_entity_mentions_session", "session_id"),
        Index("ix_entity_mentions_user_session", "user_id", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("capture_sessions.id", ondelete="CASCADE"), nullable=False)
    extraction_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("ai_extractions.id", ondelete="SET NULL"), nullable=True)
    context_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    entity = relationship("Entity", back_populates="mentions")
