import logging
import tempfile
import time
from datetime import timedelta

from celery.exceptions import Retry
from celery import shared_task
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.capture import CaptureSession, SessionStatus
from app.models.transcript import Transcript, TranscriptSegment
from app.services.transcriber import get_transcriber
from app.utils.time import utc_now

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="app.workers.tasks.process_session_transcription")
def process_session_transcription(self, session_id: str) -> dict:
    db = SessionLocal()
    started = time.perf_counter()

    try:
        session = db.scalar(select(CaptureSession).where(CaptureSession.id == session_id))
        if not session:
            logger.error("Session not found for transcription: %s", session_id)
            return {"status": "error", "reason": "session_not_found"}

        session.status = SessionStatus.transcribing.value
        session.error_message = None
        db.commit()

        wav_bytes = session.audio_blob_wav
        if wav_bytes is None or len(wav_bytes) < 44:
            session.status = SessionStatus.failed.value
            session.error_message = "Missing direct WAV payload"
            db.commit()
            return {"status": "error", "reason": "missing_direct_wav"}

        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(wav_bytes)
            tmp.flush()
            transcriber = get_transcriber()
            result = transcriber.transcribe(tmp.name)

        transcript = db.scalar(select(Transcript).where(Transcript.session_id == session.id))
        if not transcript:
            transcript = Transcript(
                session_id=session.id,
                model_name=result["model_name"],
                language=result.get("language"),
                full_text=result.get("full_text", ""),
                duration_seconds=result.get("duration_seconds"),
            )
            db.add(transcript)
            db.flush()
        else:
            transcript.model_name = result["model_name"]
            transcript.language = result.get("language")
            transcript.full_text = result.get("full_text", "")
            transcript.duration_seconds = result.get("duration_seconds")
            db.execute(delete(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript.id))

        for seg in result.get("segments", []):
            db.add(
                TranscriptSegment(
                    transcript_id=transcript.id,
                    segment_index=seg["segment_index"],
                    start_seconds=seg["start_seconds"],
                    end_seconds=seg["end_seconds"],
                    text=seg["text"],
                )
            )

        session.status = SessionStatus.done.value
        session.error_message = None
        session.finalized_at = session.finalized_at or utc_now()
        db.commit()

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info("Transcription completed session=%s chunks=%s elapsed_ms=%s", session.id, session.total_chunks, elapsed_ms)

        return {"status": "ok", "session_id": session.id}

    except Retry:
        raise

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        session = db.scalar(select(CaptureSession).where(CaptureSession.id == session_id))
        # Retry transient failures with exponential backoff.
        if session and self.request.retries < 5:
            retry_count = self.request.retries + 1
            countdown = min(300, 15 * (2 ** self.request.retries))
            session.status = SessionStatus.queued.value
            session.error_message = f"transcription_retry_{retry_count}: {str(exc)[:220]}"
            db.commit()
            logger.warning(
                "Transcription retry scheduled session=%s retry=%s countdown=%ss error=%s",
                session_id,
                retry_count,
                countdown,
                exc,
            )
            raise self.retry(exc=exc, countdown=countdown)

        if session:
            session.status = SessionStatus.failed.value
            session.error_message = str(exc)
            db.commit()
        logger.exception("Failed transcription for session %s", session_id)
        return {"status": "error", "reason": str(exc)}

    finally:
        db.close()


@shared_task(bind=True, name="app.workers.tasks.recover_stuck_transcriptions")
def recover_stuck_transcriptions(self, limit: int = 100) -> dict:
    """
    Requeue stale transcribing sessions and all queued sessions.
    Safe to run multiple times.
    """
    db = SessionLocal()
    try:
        now = utc_now()
        stale_cutoff = now - timedelta(minutes=5)
        clamped_limit = max(1, min(limit, 500))

        stale_sessions = db.scalars(
            select(CaptureSession).where(
                CaptureSession.status == SessionStatus.transcribing.value,
                CaptureSession.finalized_at.is_not(None),
                CaptureSession.finalized_at < stale_cutoff,
            ).limit(clamped_limit)
        ).all()

        for session in stale_sessions:
            session.status = SessionStatus.queued.value
            session.error_message = "recovered_from_stale_transcribing"

        queued_ids = db.scalars(
            select(CaptureSession.id).where(CaptureSession.status == SessionStatus.queued.value).limit(clamped_limit)
        ).all()
        db.commit()

        enqueued = 0
        for sid in queued_ids:
            self.app.send_task("app.workers.tasks.process_session_transcription", args=[sid], queue="transcription")
            enqueued += 1

        return {"status": "ok", "stale_recovered": len(stale_sessions), "enqueued": enqueued}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Failed recovering stuck transcriptions")
        return {"status": "error", "reason": str(exc)}
    finally:
        db.close()
