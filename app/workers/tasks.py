import logging
import tempfile

from celery import shared_task
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.capture import AudioChunk, CaptureSession, SessionStatus
from app.models.transcript import Transcript, TranscriptSegment
from app.services.audio import pcm_chunks_to_wav
from app.services.storage import get_storage
from app.services.transcriber import get_transcriber

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="app.workers.tasks.process_session_transcription")
def process_session_transcription(self, session_id: str) -> dict:
    db = SessionLocal()
    storage = get_storage()

    try:
        session = db.scalar(select(CaptureSession).where(CaptureSession.id == session_id))
        if not session:
            logger.error("Session not found for transcription: %s", session_id)
            return {"status": "error", "reason": "session_not_found"}

        session.status = SessionStatus.transcribing.value
        session.error_message = None
        db.commit()

        chunks = db.scalars(
            select(AudioChunk).where(AudioChunk.session_id == session_id).order_by(AudioChunk.chunk_index.asc())
        ).all()

        if not chunks:
            session.status = SessionStatus.failed.value
            session.error_message = "No chunks found"
            db.commit()
            return {"status": "error", "reason": "no_chunks"}

        chunk_bytes = [storage.get_bytes(chunk.object_key) for chunk in chunks]
        wav_bytes = pcm_chunks_to_wav(
            chunk_bytes=chunk_bytes,
            sample_rate=session.sample_rate,
            channels=session.channels,
            sample_width_bytes=2,
        )

        assembled_key = f"assembled/{session.id}/full.wav"
        storage.put_bytes(assembled_key, wav_bytes, content_type="audio/wav")
        session.assembled_object_key = assembled_key
        db.commit()

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
        db.commit()

        return {"status": "ok", "session_id": session.id}

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        session = db.scalar(select(CaptureSession).where(CaptureSession.id == session_id))
        if session:
            session.status = SessionStatus.failed.value
            session.error_message = str(exc)
            db.commit()
        logger.exception("Failed transcription for session %s", session_id)
        return {"status": "error", "reason": str(exc)}

    finally:
        db.close()
