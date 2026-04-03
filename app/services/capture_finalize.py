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
    chunk_bytes: list[bytes] = []
    for chunk in chunks:
        if chunk.pcm_data is not None:
            chunk_bytes.append(bytes(chunk.pcm_data))
            continue
        if chunk.object_key:
            chunk_bytes.append(storage.get_bytes(chunk.object_key))
            continue
        raise ValueError("Audio chunk has neither pcm_data nor object_key")

    wav_bytes = pcm_chunks_to_wav(
        chunk_bytes=chunk_bytes,
        sample_rate=session.sample_rate,
        channels=session.channels,
        sample_width_bytes=2,
    )

    session.audio_blob_wav = wav_bytes
    session.audio_blob_content_type = "audio/wav"
    session.audio_blob_size_bytes = len(wav_bytes)
    session.total_chunks = len(chunks)
    session.status = SessionStatus.queued.value
    session.error_message = None
    session.finalized_at = utc_now()
    db.commit()

    return len(chunks)
