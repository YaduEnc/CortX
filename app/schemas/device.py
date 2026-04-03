from datetime import datetime

from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    device_code: str = Field(min_length=3, max_length=128)
    secret: str = Field(min_length=8, max_length=255)


class DeviceAuthRequest(BaseModel):
    device_code: str = Field(min_length=3, max_length=128)
    secret: str = Field(min_length=8, max_length=255)


class DeviceResponse(BaseModel):
    id: str
    device_code: str
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class DeviceCaptureUploadResponse(BaseModel):
    session_id: str
    status: str
    queued_for_transcription: bool
    audio_size_bytes: int
    sample_rate: int
    channels: int
    codec: str


class DeviceCaptureSessionStartRequest(BaseModel):
    sample_rate: int = Field(default=16000, ge=8000, le=48000)
    channels: int = Field(default=1, ge=1, le=2)
    codec: str = Field(default="pcm16le", min_length=1, max_length=32)


class DeviceCaptureSessionStartResponse(BaseModel):
    session_id: str
    status: str
    sample_rate: int
    channels: int
    codec: str


class DeviceCaptureChunkUploadResponse(BaseModel):
    session_id: str
    chunk_index: int
    status: str
    ack_seq: int
    next_seq: int
    total_chunks: int
    byte_size: int


class DeviceCaptureFinalizeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class DeviceCaptureFinalizeResponse(BaseModel):
    session_id: str
    status: str
    total_chunks: int
    queued_for_transcription: bool


class DeviceHeartbeatRequest(BaseModel):
    firmware_version: str | None = Field(default=None, max_length=64)


class DeviceHeartbeatResponse(BaseModel):
    status: str
    device_id: str
    last_seen_at: datetime
    firmware_version: str | None
