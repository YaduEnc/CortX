import logging
from datetime import timedelta

from celery import Celery
from celery.signals import worker_process_init, worker_ready
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.assistant import AIExtraction, AIExtractionStatus
from app.models.capture import CaptureSession, SessionStatus
from app.utils.time import utc_now

settings = get_settings()
logger = logging.getLogger(__name__)

celery_app = Celery(
    "secondmind",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "app.workers.tasks.process_session_transcription": {"queue": "transcription"},
        "app.workers.tasks.process_session_ai_extraction": {"queue": "ai"},
        "app.workers.tasks.recover_stuck_transcriptions": {"queue": "transcription"},
    },
)


@worker_process_init.connect
def _prewarm_transcriber(**_: object) -> None:
    """
    Preload faster-whisper model at worker boot so first transcription task
    does not pay model-download/init latency.
    """
    try:
        from app.services.transcriber import get_transcriber

        transcriber = get_transcriber()
        logger.info("Transcriber prewarmed: model=%s", transcriber.model_name)
    except Exception:  # noqa: BLE001
        logger.exception("Transcriber prewarm failed; worker will retry lazily on first task")


@worker_ready.connect
def _requeue_backlog(sender=None, **_: object) -> None:
    """
    On worker startup, requeue any pending sessions and recover stale
    transcribing sessions that may have been left behind by restarts.
    """
    db = SessionLocal()
    try:
        now = utc_now()
        stale_cutoff = now - timedelta(minutes=5)

        stale_ids = db.scalars(
            select(CaptureSession.id).where(
                CaptureSession.status == SessionStatus.transcribing.value,
                CaptureSession.finalized_at.is_not(None),
                CaptureSession.finalized_at < stale_cutoff,
            )
        ).all()
        for sid in stale_ids:
            session = db.scalar(select(CaptureSession).where(CaptureSession.id == sid))
            if session:
                session.status = SessionStatus.queued.value
                session.error_message = "recovered_from_stale_transcribing"

        queued_ids = db.scalars(
            select(CaptureSession.id).where(CaptureSession.status == SessionStatus.queued.value).limit(100)
        ).all()
        db.commit()

        for sid in queued_ids:
            celery_app.send_task("app.workers.tasks.process_session_transcription", args=[sid], queue="transcription")

        ai_stale_cutoff = now - timedelta(minutes=5)
        stale_ai = db.scalars(
            select(AIExtraction.id).where(
                AIExtraction.status == AIExtractionStatus.processing.value,
                AIExtraction.started_at.is_not(None),
                AIExtraction.started_at < ai_stale_cutoff,
            )
        ).all()
        for extraction_id in stale_ai:
            extraction = db.scalar(select(AIExtraction).where(AIExtraction.id == extraction_id))
            if extraction:
                extraction.status = AIExtractionStatus.queued.value
                extraction.error_message = "recovered_from_stale_processing"

        queued_ai = db.scalars(
            select(AIExtraction.session_id).where(AIExtraction.status == AIExtractionStatus.queued.value).limit(100)
        ).all()
        db.commit()
        for sid in queued_ai:
            celery_app.send_task("app.workers.tasks.process_session_ai_extraction", args=[sid], queue="ai")

        if stale_ids or queued_ids or stale_ai or queued_ai:
            logger.info(
                "Backlog recovery queued transcription(stale=%s queued=%s) ai(stale=%s queued=%s)",
                len(stale_ids),
                len(queued_ids),
                len(stale_ai),
                len(queued_ai),
            )
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("Transcription backlog recovery failed")
    finally:
        db.close()
