from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.capture import AudioChunk, CaptureSession, SessionStatus
from app.services.audio import pcm_chunks_to_wav
from app.services.storage import get_storage
from app.utils.time import utc_now


def assemble_capture_session(db: Session, session: CaptureSession) -> int:
    chunks = db.scalars(
        select(AudioChunk).where(AudioChunk.session_id == session.id).order_by(AudioChunk.chunk_index.asc())
    ).all()
    if not chunks:
        raise ValueError("Cannot finalize empty session")

    storage = get_storage()
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
    session.total_chunks = len(chunks)
    session.status = SessionStatus.done.value
    session.error_message = None
    session.finalized_at = utc_now()
    db.commit()

    return len(chunks)
