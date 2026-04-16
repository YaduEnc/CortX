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
            local_files_only=False,
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
            initial_prompt=(
                "This is a conversation that may include English, Hindi, Hinglish (Hindi-English code-switching), "
                "or a mix of both languages. Transcribe all spoken words accurately in their original language. "
                "Hindi words should be transcribed in Devanagari script or romanized Hindi. "
                "Capture everything spoken, including filler words and incomplete sentences."
            ),
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

        # If output is valid, return immediately
        if not _is_garbage_transcript(result["full_text"]) or language is not None:
            return result

        detected_lang = result.get("language")

        # --- Retry chain for garbage output ---

        # Retry 1: Force English (unless auto-detect already picked English)
        if detected_lang != "en":
            logger.info(
                "Retrying transcription with language='en' (detected: %s)",
                detected_lang,
            )
            en_result = self._run_transcribe(
                audio_path,
                vad_filter=vad_filter,
                beam_size=beam_size,
                language="en",
            )
            if not _is_garbage_transcript(en_result["full_text"]):
                logger.info("English retry succeeded: text_len=%d", len(en_result["full_text"]))
                return en_result

        # Retry 2: Force Hindi (unless auto-detect already picked Hindi)
        if detected_lang != "hi":
            logger.info(
                "Retrying transcription with language='hi' (detected: %s)",
                detected_lang,
            )
            hi_result = self._run_transcribe(
                audio_path,
                vad_filter=vad_filter,
                beam_size=beam_size,
                language="hi",
            )
            if not _is_garbage_transcript(hi_result["full_text"]):
                logger.info("Hindi retry succeeded: text_len=%d", len(hi_result["full_text"]))
                return hi_result

        # Retry 3: Disable VAD filter (it can aggressively strip valid speech)
        if vad_filter:
            logger.info("Retrying transcription with VAD disabled (all retries with VAD produced garbage)")
            no_vad_result = self._run_transcribe(
                audio_path,
                vad_filter=False,
                beam_size=beam_size,
                language=None,
            )
            if not _is_garbage_transcript(no_vad_result["full_text"]):
                logger.info("No-VAD retry succeeded: text_len=%d", len(no_vad_result["full_text"]))
                return no_vad_result

        logger.warning(
            "All transcription retries produced garbage (detected_lang=%s). Using original result.",
            detected_lang,
        )
        return result


@lru_cache(maxsize=1)
def get_transcriber() -> LocalWhisperTranscriber:
    return LocalWhisperTranscriber()

