from datetime import datetime

from pydantic import BaseModel, Field


class AppAssistantItemResponse(BaseModel):
    item_id: str
    extraction_id: str
    session_id: str
    transcript_id: str
    item_type: str
    title: str
    details: str | None
    due_at: datetime | None
    timezone: str | None
    priority: int | None
    status: str
    source_segment_start_seconds: float | None
    source_segment_end_seconds: float | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class AppCaptureAIExtractionResponse(BaseModel):
    extraction_id: str
    session_id: str
    transcript_id: str
    status: str
    intent: str | None
    intent_confidence: float | None
    summary: str | None
    plan_steps: list[dict]
    model_name: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime


class AppCaptureAIResponse(BaseModel):
    session_id: str
    transcript_ready: bool
    extraction: AppCaptureAIExtractionResponse | None
    items: list[AppAssistantItemResponse]


class AppAssistantItemUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|done|dismissed|snoozed)$")
    due_at: datetime | None = None
    timezone: str | None = Field(default=None, max_length=64)
    snooze_minutes: int | None = Field(default=None, ge=1, le=10080)


class AppCaptureAIReprocessResponse(BaseModel):
    session_id: str
    extraction_id: str
    status: str
    queued: bool


class AIPipelineMetricsResponse(BaseModel):
    status_counts: dict[str, int]
    avg_done_latency_ms: int | None
    last_error: str | None
    updated_at: datetime
