from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    sessions = relationship("CaptureSession", back_populates="device", cascade="all, delete-orphan")
    user_binding = relationship("DeviceUserBinding", back_populates="device", uselist=False, cascade="all, delete-orphan")
    pairing_sessions = relationship("PairingSession", back_populates="device", cascade="all, delete-orphan")
