from functools import lru_cache
import os

from faster_whisper import WhisperModel

from app.core.config import get_settings


class LocalWhisperTranscriber:
    def __init__(self) -> None:
        settings = get_settings()
        model_path = (settings.whisper_model_path or "").strip()
        model_ref = model_path or settings.whisper_model_size
        if model_path and not os.path.isdir(model_path):
            raise RuntimeError(f"Configured WHISPER_MODEL_PATH does not exist: {model_path}")

        self.model_name = model_ref
        self.model = WhisperModel(
            model_ref,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            download_root=(settings.whisper_download_root or None),
        )

    def transcribe(
        self,
        audio_path: str,
        *,
        vad_filter: bool = True,
        beam_size: int = 1,
        language: str | None = None,
    ) -> dict:
        segments_iter, info = self.model.transcribe(
            audio_path,
            vad_filter=vad_filter,
            beam_size=beam_size,
            language=language,
            condition_on_previous_text=False,
        )

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
