from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AppRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)


class AppAuthRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)


class AppForgotPasswordRequest(BaseModel):
    email: EmailStr


class AppForgotPasswordRequestResponse(BaseModel):
    status: str
    message: str
    expires_in_seconds: int | None = None
    reset_token: str | None = None


class AppForgotPasswordConfirmRequest(BaseModel):
    email: EmailStr
    reset_token: str = Field(min_length=12, max_length=255)
    new_password: str = Field(min_length=8, max_length=255)


class AppDeleteAccountRequest(BaseModel):
    password: str = Field(min_length=8, max_length=255)


class AppActionStatusResponse(BaseModel):
    status: str
    message: str


class AppTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class AppMeResponse(BaseModel):
    user_id: str
    email: EmailStr
    full_name: str | None
    has_avatar: bool
    avatar_updated_at: datetime | None = None
    created_at: datetime


class AppMeUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)


class AppUserPreferencesResponse(BaseModel):
    timezone: str
    daily_summary_enabled: bool
    reminder_notifications_enabled: bool
    calendar_export_default_enabled: bool
    updated_at: datetime


class AppUserPreferencesUpdateRequest(BaseModel):
    timezone: str | None = Field(default=None, max_length=64)
    daily_summary_enabled: bool | None = None
    reminder_notifications_enabled: bool | None = None
    calendar_export_default_enabled: bool | None = None


class PairedDeviceResponse(BaseModel):
    device_id: str
    device_code: str
    alias: str | None
    paired_at: datetime
    last_seen_at: datetime | None = None
    status: str
    firmware_version: str | None = None
    last_capture_at: datetime | None = None


class AppDeviceUpdateRequest(BaseModel):
    alias: str | None = Field(default=None, max_length=128)


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


class AppCaptureUploadResponse(BaseModel):
    session_id: str
    status: str
    queued_for_transcription: bool
    audio_size_bytes: int
    sample_rate: int
    channels: int
    codec: str


class AppDailySummaryFocusItem(BaseModel):
    item_id: str
    item_type: str
    title: str
    due_at: datetime | None
    status: str
    session_id: str
    device_code: str | None = None


class AppDailySummaryDeviceBreakdown(BaseModel):
    device_id: str
    device_code: str
    memories_count: int
    transcript_ready_count: int
    open_action_count: int
    upcoming_event_count: int


class AppDailySummaryMetrics(BaseModel):
    memories_count: int
    transcript_ready_count: int
    open_actions_due_count: int
    upcoming_events_count: int
    top_intent: str | None
    device_count: int


class AppDailySummaryResponse(BaseModel):
    date: str
    timezone: str
    headline: str
    generated_at: datetime
    metrics: AppDailySummaryMetrics
    focus_items: list[AppDailySummaryFocusItem]
    device_breakdown: list[AppDailySummaryDeviceBreakdown]


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
