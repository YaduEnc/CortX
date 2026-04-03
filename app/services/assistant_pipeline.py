from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.assistant import AIExtraction, AIExtractionStatus, AIItem
from app.models.capture import CaptureSession
from app.models.pairing import DeviceUserBinding
from app.models.transcript import Transcript
from app.utils.time import utc_now


class AssistantPipelineError(ValueError):
    pass


def prepare_extraction_record(db: Session, session_id: str, *, force_reset: bool = False) -> tuple[CaptureSession, Transcript, AIExtraction]:
    session = db.scalar(select(CaptureSession).where(CaptureSession.id == session_id))
    if not session:
        raise AssistantPipelineError("Capture session not found")

    transcript = db.scalar(select(Transcript).where(Transcript.session_id == session.id))
    if not transcript:
        raise AssistantPipelineError("Transcript not ready")

    binding = db.scalar(
        select(DeviceUserBinding).where(
            DeviceUserBinding.device_id == session.device_id,
            DeviceUserBinding.is_active.is_(True),
        )
    )
    if not binding:
        raise AssistantPipelineError("Device is not paired with an active user")

    extraction = db.scalar(select(AIExtraction).where(AIExtraction.transcript_id == transcript.id))
    if not extraction:
        extraction = AIExtraction(
            user_id=binding.user_id,
            session_id=session.id,
            transcript_id=transcript.id,
            status=AIExtractionStatus.queued.value,
        )
        db.add(extraction)
        db.flush()
    else:
        extraction.user_id = binding.user_id
        extraction.session_id = session.id
        extraction.transcript_id = transcript.id

    if force_reset:
        db.execute(delete(AIItem).where(AIItem.extraction_id == extraction.id))
        extraction.status = AIExtractionStatus.queued.value
        extraction.intent = None
        extraction.intent_confidence = None
        extraction.summary = None
        extraction.plan_json = None
        extraction.raw_json = None
        extraction.error_message = None
        extraction.started_at = None
        extraction.completed_at = None
        extraction.model_name = None
        extraction.updated_at = utc_now()

    return session, transcript, extraction
