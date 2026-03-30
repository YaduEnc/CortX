from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AppRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)


class AppAuthRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)


class AppTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class PairedDeviceResponse(BaseModel):
    device_id: str
    device_code: str
    alias: str | None
    paired_at: datetime


class AppCaptureListItemResponse(BaseModel):
    session_id: str
    device_id: str
    device_code: str
    status: str
    total_chunks: int
    started_at: datetime
    finalized_at: datetime | None
    duration_seconds: float | None
    has_audio: bool


class AppCaptureTranscriptResponse(BaseModel):
    session_id: str
    model_name: str
    language: str | None
    full_text: str
    duration_seconds: float | None


class AppLiveStreamStartRequest(BaseModel):
    device_code: str = Field(min_length=3, max_length=128)
    sample_rate: int = Field(default=8000, ge=8000, le=48000)
    channels: int = Field(default=1, ge=1, le=2)
    codec: str = Field(default="pcm16le", min_length=3, max_length=32)
    frame_duration_ms: int = Field(default=500, ge=100, le=2000)


class AppLiveStreamStartResponse(BaseModel):
    session_id: str
    stream_token: str
    ws_url: str
    status: str
    sample_rate: int
    channels: int
    codec: str
    frame_duration_ms: int
    expires_at: datetime
