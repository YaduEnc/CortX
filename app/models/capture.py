from datetime import datetime, timezone
from enum import Enum
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SessionStatus(str, Enum):
    receiving = "receiving"
    queued = "queued"
    transcribing = "transcribing"
    done = "done"
    failed = "failed"


class CaptureSession(Base):
    __tablename__ = "capture_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default=SessionStatus.receiving.value, nullable=False, index=True)
    sample_rate: Mapped[int] = mapped_column(Integer, default=16000, nullable=False)
    channels: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    codec: Mapped[str] = mapped_column(String(32), default="pcm16le", nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assembled_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_blob_wav: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    audio_blob_content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audio_blob_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    memory_gist: Mapped[str | None] = mapped_column(String(240), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    device = relationship("Device", back_populates="sessions")
    chunks = relationship("AudioChunk", back_populates="session", cascade="all, delete-orphan")
    transcript = relationship("Transcript", back_populates="session", uselist=False, cascade="all, delete-orphan")
    ai_extraction = relationship("AIExtraction", back_populates="session", uselist=False, cascade="all, delete-orphan")
    pending_actions = relationship("PendingAction", back_populates="session")


class AudioChunk(Base):
    __tablename__ = "audio_chunks"
    __table_args__ = (
        UniqueConstraint("session_id", "chunk_index", name="uq_session_chunk_index"),
        Index("ix_audio_chunks_session_index", "session_id", "chunk_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("capture_sessions.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    channels: Mapped[int] = mapped_column(Integer, nullable=False)
    codec: Mapped[str] = mapped_column(String(32), nullable=False)
    crc32: Mapped[str | None] = mapped_column(String(16), nullable=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    pcm_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    session = relationship("CaptureSession", back_populates="chunks")
