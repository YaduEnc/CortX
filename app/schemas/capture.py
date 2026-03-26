from datetime import datetime

from pydantic import BaseModel


class SessionCreateRequest(BaseModel):
    sample_rate: int = 16000
    channels: int = 1
    codec: str = "pcm16le"


class SessionCreateResponse(BaseModel):
    session_id: str
    status: str
    started_at: datetime


class ChunkUploadResponse(BaseModel):
    session_id: str
    chunk_index: int
    status: str
    next_expected_chunk: int


class SessionFinalizeResponse(BaseModel):
    session_id: str
    status: str


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    total_chunks: int
    error_message: str | None
    started_at: datetime
    finalized_at: datetime | None


class TranscriptSegmentResponse(BaseModel):
    segment_index: int
    start_seconds: float
    end_seconds: float
    text: str


class TranscriptResponse(BaseModel):
    session_id: str
    model_name: str
    language: str | None
    full_text: str
    duration_seconds: float | None
    segments: list[TranscriptSegmentResponse]
