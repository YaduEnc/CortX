from functools import lru_cache
import logging
import os
import re

from faster_whisper import WhisperModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _is_garbage_transcript(text: str) -> bool:
    """Detect if a transcript is likely garbage/hallucination from Whisper.
    
    Common signs: mostly punctuation/dandas (।), random Unicode mixing,
    repetitive characters, or very low alphanumeric ratio.
    """
    if not text or not text.strip():
        return True
    
    cleaned = text.strip()
    # Count actual alphanumeric characters (Latin + Devanagari + Arabic digits)
    alphanumeric = len(re.findall(r'[a-zA-Z0-9\u0900-\u097F]', cleaned))
    total = len(cleaned.replace(' ', ''))
    
    if total == 0:
        return True
    
    ratio = alphanumeric / total
    
    # If less than 30% of non-space characters are real letters/digits, it's garbage
    if ratio < 0.30:
        logger.warning(
            "Garbage transcript detected: alphanumeric_ratio=%.2f text_preview=%s",
            ratio,
            cleaned[:100],
        )
        return True
    
    # Check for excessive repetition (e.g., "।।।।।।।।।।")
    unique_chars = set(cleaned.replace(' ', ''))
    if len(unique_chars) <= 3 and total > 5:
        logger.warning("Garbage transcript detected: only %d unique characters", len(unique_chars))
        return True
    
    return False


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
            local_files_only=True,
        )

    def _run_transcribe(
        self,
        audio_path: str,
        *,
        vad_filter: bool = True,
        beam_size: int = 5,
        language: str | None = None,
    ) -> dict:
        segments_iter, info = self.model.transcribe(
            audio_path,
            vad_filter=vad_filter,
            beam_size=beam_size,
            language=language,
            word_timestamps=True,
            best_of=3,
            patience=1.5,
            initial_prompt="This is a conversation in English, Hindi, or Hinglish (Hindi-English mix). Transcribe the spoken words accurately. Extract tasks and reminders if present.",
            condition_on_previous_text=True,
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

    def transcribe(
        self,
        audio_path: str,
        *,
        vad_filter: bool = True,
        beam_size: int = 5,
        language: str | None = None,
    ) -> dict:
        # First attempt: auto language detection
        result = self._run_transcribe(
            audio_path,
            vad_filter=vad_filter,
            beam_size=beam_size,
            language=language,
        )

        logger.info(
            "Transcription first pass: language=%s duration=%.1fs segments=%d text_len=%d",
            result["language"],
            result["duration_seconds"],
            len(result["segments"]),
            len(result["full_text"]),
        )

        # If garbage detected and language wasn't forced, retry with English
        if _is_garbage_transcript(result["full_text"]) and language is None:
            logger.info(
                "Retrying transcription with language='en' due to garbage output (detected: %s)",
                result["language"],
            )
            retry_result = self._run_transcribe(
                audio_path,
                vad_filter=vad_filter,
                beam_size=beam_size,
                language="en",
            )

            # Use retry if it produced better output
            if not _is_garbage_transcript(retry_result["full_text"]):
                logger.info(
                    "English retry succeeded: text_len=%d",
                    len(retry_result["full_text"]),
                )
                return retry_result
            else:
                logger.warning(
                    "English retry also produced garbage. Using original result."
                )

        return result


@lru_cache(maxsize=1)
def get_transcriber() -> LocalWhisperTranscriber:
    return LocalWhisperTranscriber()

