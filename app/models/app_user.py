from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, DateTime, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    avatar_content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    avatar_file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avatar_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    device_bindings = relationship("DeviceUserBinding", back_populates="user", cascade="all, delete-orphan")
    pairing_sessions = relationship("PairingSession", back_populates="user", cascade="all, delete-orphan")
    password_reset_tokens = relationship("AppPasswordResetToken", back_populates="user", cascade="all, delete-orphan")
    ai_extractions = relationship("AIExtraction", back_populates="user", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="user", cascade="all, delete-orphan")
    pending_actions = relationship("PendingAction", back_populates="user", cascade="all, delete-orphan")
    preferences = relationship("AppUserPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan")
    founder_ideas = relationship("FounderIdeaCluster", back_populates="user", cascade="all, delete-orphan")
    weekly_founder_memos = relationship("WeeklyFounderMemo", back_populates="user", cascade="all, delete-orphan")
    memory_links = relationship("MemoryLink", back_populates="user", cascade="all, delete-orphan")
