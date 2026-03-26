from functools import lru_cache

from faster_whisper import WhisperModel

from app.core.config import get_settings


class LocalWhisperTranscriber:
    def __init__(self) -> None:
        settings = get_settings()
        self.model_name = settings.whisper_model_size
        self.model = WhisperModel(
            settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )

    def transcribe(self, audio_path: str) -> dict:
        segments_iter, info = self.model.transcribe(audio_path, vad_filter=True, beam_size=1)

        segments = []
        full_text_parts: list[str] = []
        duration_seconds = 0.0

        for idx, segment in enumerate(segments_iter):
            seg_text = segment.text.strip()
            full_text_parts.append(seg_text)
            duration_seconds = max(duration_seconds, float(segment.end))
            segments.append(
                {
                    "segment_index": idx,
                    "start_seconds": float(segment.start),
                    "end_seconds": float(segment.end),
                    "text": seg_text,
                }
            )

        return {
            "model_name": self.model_name,
            "language": info.language,
            "full_text": " ".join(part for part in full_text_parts if part),
            "duration_seconds": duration_seconds,
            "segments": segments,
        }


@lru_cache(maxsize=1)
def get_transcriber() -> LocalWhisperTranscriber:
    return LocalWhisperTranscriber()
