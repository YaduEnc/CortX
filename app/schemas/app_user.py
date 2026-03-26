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
