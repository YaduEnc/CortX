from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_device
from app.db.session import get_db
from app.models.capture import AudioChunk, CaptureSession, SessionStatus
from app.models.device import Device
from app.models.transcript import Transcript
from app.schemas.capture import (
    ChunkUploadResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionFinalizeResponse,
    SessionStatusResponse,
    TranscriptResponse,
    TranscriptSegmentResponse,
)
from app.services.storage import get_storage
from app.utils.crc import crc32_hex
from app.utils.time import utc_now
from app.core.config import get_settings
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/capture", tags=["capture"])
settings = get_settings()


def _compute_next_expected(indices: set[int]) -> int:
    expected = 0
    while expected in indices:
        expected += 1
    return expected


@router.post("/sessions", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreateRequest,
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> SessionCreateResponse:
    session = CaptureSession(
        device_id=device.id,
        sample_rate=payload.sample_rate,
        channels=payload.channels,
        codec=payload.codec,
        status=SessionStatus.receiving.value,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return SessionCreateResponse(session_id=session.id, status=session.status, started_at=session.started_at)


@router.post("/chunks", response_model=ChunkUploadResponse)
def upload_chunk(
    session_id: str = Form(...),
    chunk_index: int = Form(..., ge=0),
    start_ms: int = Form(..., ge=0),
    end_ms: int = Form(..., ge=0),
    sample_rate: int = Form(..., ge=8000),
    channels: int = Form(default=1, ge=1, le=2),
    codec: str = Form(default="pcm16le"),
    crc32: str | None = Form(default=None),
    audio_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> ChunkUploadResponse:
    session = db.scalar(
        select(CaptureSession).where(
            CaptureSession.id == session_id,
            CaptureSession.device_id == device.id,
        )
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.status != SessionStatus.receiving.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session not accepting chunks")

    payload = audio_file.file.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty chunk")

    max_chunk_bytes = settings.max_chunk_bytes
    if len(payload) > max_chunk_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Chunk too large")

    computed_crc = crc32_hex(payload)
    if crc32 and crc32.lower() != computed_crc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CRC mismatch")

    existing = db.scalar(
        select(AudioChunk).where(AudioChunk.session_id == session_id, AudioChunk.chunk_index == chunk_index)
    )
    if existing:
        existing_indices = {
            idx
            for (idx,) in db.execute(
                select(AudioChunk.chunk_index).where(AudioChunk.session_id == session_id)
            ).all()
        }
        next_expected = _compute_next_expected(existing_indices)
        return ChunkUploadResponse(
            session_id=session_id,
            chunk_index=chunk_index,
            status="duplicate",
            next_expected_chunk=next_expected,
        )

    object_key = f"raw/{session_id}/{chunk_index:06d}.pcm"
    storage = get_storage()
    storage.put_bytes(object_key, payload, content_type="application/octet-stream")

    chunk = AudioChunk(
        session_id=session_id,
        chunk_index=chunk_index,
        start_ms=start_ms,
        end_ms=end_ms,
        sample_rate=sample_rate,
        channels=channels,
        codec=codec,
        crc32=computed_crc,
        byte_size=len(payload),
        object_key=object_key,
    )
    db.add(chunk)

    if chunk_index + 1 > session.total_chunks:
        session.total_chunks = chunk_index + 1

    db.commit()

    existing_indices = {
        idx
        for (idx,) in db.execute(select(AudioChunk.chunk_index).where(AudioChunk.session_id == session_id)).all()
    }
    next_expected = _compute_next_expected(existing_indices)

    return ChunkUploadResponse(
        session_id=session_id,
        chunk_index=chunk_index,
        status="accepted",
        next_expected_chunk=next_expected,
    )


@router.post("/sessions/{session_id}/finalize", response_model=SessionFinalizeResponse)
def finalize_session(
    session_id: str,
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> SessionFinalizeResponse:
    session = db.scalar(
        select(CaptureSession).where(
            CaptureSession.id == session_id,
            CaptureSession.device_id == device.id,
        )
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.status in {SessionStatus.queued.value, SessionStatus.transcribing.value, SessionStatus.done.value}:
        return SessionFinalizeResponse(session_id=session.id, status=session.status)

    chunk_count = db.scalar(select(func.count(AudioChunk.id)).where(AudioChunk.session_id == session.id))
    if chunk_count == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot finalize empty session")

    session.status = SessionStatus.queued.value
    session.finalized_at = utc_now()
    db.commit()

    celery_app.send_task("app.workers.tasks.process_session_transcription", args=[session.id])

    return SessionFinalizeResponse(session_id=session.id, status=session.status)


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
def session_status(
    session_id: str,
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> SessionStatusResponse:
    session = db.scalar(
        select(CaptureSession).where(
            CaptureSession.id == session_id,
            CaptureSession.device_id == device.id,
        )
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return SessionStatusResponse(
        session_id=session.id,
        status=session.status,
        total_chunks=session.total_chunks,
        error_message=session.error_message,
        started_at=session.started_at,
        finalized_at=session.finalized_at,
    )


@router.get("/sessions/{session_id}/transcript", response_model=TranscriptResponse)
def get_transcript(
    session_id: str,
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> TranscriptResponse:
    session = db.scalar(
        select(CaptureSession)
        .where(CaptureSession.id == session_id, CaptureSession.device_id == device.id)
        .options(selectinload(CaptureSession.transcript).selectinload(Transcript.segments))
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    transcript = session.transcript
    if not transcript:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not ready")

    segments = [
        TranscriptSegmentResponse(
            segment_index=segment.segment_index,
            start_seconds=segment.start_seconds,
            end_seconds=segment.end_seconds,
            text=segment.text,
        )
        for segment in sorted(transcript.segments, key=lambda x: x.segment_index)
    ]

    return TranscriptResponse(
        session_id=session.id,
        model_name=transcript.model_name,
        language=transcript.language,
        full_text=transcript.full_text,
        duration_seconds=transcript.duration_seconds,
        segments=segments,
    )
