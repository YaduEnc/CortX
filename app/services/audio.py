import io
import wave


def pcm_chunks_to_wav(
    chunk_bytes: list[bytes],
    sample_rate: int,
    channels: int = 1,
    sample_width_bytes: int = 2,
) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width_bytes)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(chunk_bytes))
    return buffer.getvalue()
