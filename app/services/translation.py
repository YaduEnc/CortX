"""
Translation service for CortX.

Translates non-English transcripts (Hindi, Hinglish, etc.) into English
using the local LM Studio instance. This ensures all memories, summaries,
and extracted intelligence are stored and displayed in English.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class TranslationError(RuntimeError):
    pass


# Languages that should bypass translation (already English).
_ENGLISH_CODES = {"en", "english"}

# Languages known to appear in CortX transcripts that need translation.
_TRANSLATABLE_CODES = {
    "hi", "hindi",
    "ur", "urdu",
    "bn", "bengali",
    "ta", "tamil",
    "te", "telugu",
    "mr", "marathi",
    "gu", "gujarati",
    "kn", "kannada",
    "ml", "malayalam",
    "pa", "punjabi",
}


def _is_already_english(text: str) -> bool:
    """Heuristic check: if >85% of alpha chars are ASCII Latin, it's English."""
    if not text or not text.strip():
        return True
    alpha_chars = re.findall(r"[a-zA-Z\u0900-\u097F\u0600-\u06FF]", text)
    if not alpha_chars:
        return True
    latin = sum(1 for c in alpha_chars if "A" <= c <= "Z" or "a" <= c <= "z")
    ratio = latin / len(alpha_chars) if alpha_chars else 1.0
    return ratio > 0.85


def needs_translation(language: str | None, text: str) -> bool:
    """Determine if a transcript needs translation to English."""
    if not text or not text.strip():
        return False
    lang = (language or "").strip().lower()
    # If Whisper detected English, skip
    if lang in _ENGLISH_CODES:
        return False
    # If detected a known translatable language, translate
    if lang in _TRANSLATABLE_CODES:
        return True
    # For unknown/other languages, check the actual text content
    return not _is_already_english(text)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts)
    return ""


def _clean_json_text(text: str) -> str:
    trimmed = text.strip()
    if trimmed.startswith("```"):
        trimmed = re.sub(r"^```(?:json)?\s*", "", trimmed)
        trimmed = re.sub(r"\s*```$", "", trimmed)
    return trimmed.strip()


def translate_to_english(
    text: str,
    source_language: str | None = None,
) -> str:
    """
    Translate text from any language to English using LM Studio.
    
    Returns the English translation, or the original text if translation fails.
    """
    settings = get_settings()
    clean_text = text.strip()
    if not clean_text:
        return text

    url = settings.lmstudio_base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.lmstudio_api_key:
        headers["Authorization"] = f"Bearer {settings.lmstudio_api_key}"

    lang_hint = source_language or "auto-detected"

    system_prompt = (
        "You are a precise, silent translation machine. Translate the following text to natural, fluent English. "
        "Rules:\n"
        "- Preserve the original meaning, tone, and intent exactly.\n"
        "- If the text is a mix of Hindi and English (Hinglish), translate only the non-English parts.\n"
        "- Keep proper nouns, names, and technical terms as-is.\n"
        "- Return ONLY the translated English text. DO NOT add any commentary, explanation, apologies, or notes.\n"
        "- If you are unsure or the text is garbled, return the original text UNCHANGED. Never explain why you couldn't translate.\n"
        "- If the text is already English, return it unchanged."
    )

    user_prompt = (
        f"Source language: {lang_hint}\n"
        f"Text to translate:\n{clean_text}"
    )

    request_payload = {
        "model": settings.lmstudio_model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=request_payload,
            timeout=settings.lmstudio_timeout_seconds,
        )
    except requests.RequestException as exc:
        logger.warning("Translation request failed, using original text: %s", exc)
        return text

    if response.status_code >= 400:
        logger.warning(
            "Translation HTTP %s, using original text: %s",
            response.status_code,
            response.text[:200],
        )
        return text

    try:
        response_json = response.json()
    except ValueError:
        logger.warning("Translation response is not JSON, using original text")
        return text

    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        logger.warning("Translation response missing choices, using original text")
        return text

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        logger.warning("Translation response missing message, using original text")
        return text

    translated = _content_to_text(message.get("content")).strip()
    if not translated:
        logger.warning("Translation returned empty content, using original text")
        return text

    # Sanity: if the "translation" is much shorter than original, something went wrong
    if len(translated) < len(clean_text) * 0.3:
        logger.warning(
            "Translation suspiciously short (original=%d translated=%d), using original",
            len(clean_text),
            len(translated),
        )
        return text

    logger.info(
        "Translation completed: lang=%s original_len=%d translated_len=%d",
        lang_hint,
        len(clean_text),
        len(translated),
    )
    return translated


def translate_segments(
    segments: list[dict],
    source_language: str | None = None,
) -> list[dict]:
    """
    Translate segment texts to English in a single batch call for efficiency.
    Returns new segment dicts with translated text.
    """
    if not segments:
        return segments

    # Collect non-empty segment texts
    texts_to_translate = [seg.get("text", "").strip() for seg in segments]
    non_empty = [(i, t) for i, t in enumerate(texts_to_translate) if t]
    
    if not non_empty:
        return segments

    # Batch translate: combine all segments into one prompt for efficiency
    combined = "\n---SEGMENT_BREAK---\n".join(t for _, t in non_empty)
    
    settings = get_settings()
    url = settings.lmstudio_base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.lmstudio_api_key:
        headers["Authorization"] = f"Bearer {settings.lmstudio_api_key}"

    system_prompt = (
        "You are a precise translator. Translate the following text segments to natural, fluent English. "
        "Each segment is separated by ---SEGMENT_BREAK---. "
        "Return the translated segments separated by the same ---SEGMENT_BREAK--- delimiter. "
        "Rules:\n"
        "- Preserve the original meaning, tone, and intent exactly.\n"
        "- If text is a mix of Hindi and English (Hinglish), translate only the non-English parts.\n"
        "- Keep proper nouns, names, and technical terms as-is.\n"
        "- Return ONLY the translated text segments with the delimiters, nothing else.\n"
        "- Maintain the exact same number of segments."
    )

    user_prompt = (
        f"Source language: {source_language or 'auto-detected'}\n"
        f"Segments:\n{combined}"
    )

    try:
        response = requests.post(
            url,
            headers=headers,
            json={
                "model": settings.lmstudio_model,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=settings.lmstudio_timeout_seconds,
        )
        if response.status_code >= 400:
            raise TranslationError(f"HTTP {response.status_code}")

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise TranslationError("No choices")

        content = _content_to_text(choices[0].get("message", {}).get("content")).strip()
        translated_parts = content.split("---SEGMENT_BREAK---")
        translated_parts = [p.strip() for p in translated_parts]

        # Map back to segments
        result = [dict(seg) for seg in segments]
        if len(translated_parts) == len(non_empty):
            for (orig_idx, _), translated_text in zip(non_empty, translated_parts):
                if translated_text:
                    result[orig_idx]["text"] = translated_text
        else:
            logger.warning(
                "Segment translation count mismatch: expected=%d got=%d, falling back to full-text translation",
                len(non_empty),
                len(translated_parts),
            )
            # Fallback: translate each segment individually
            for orig_idx, orig_text in non_empty:
                translated = translate_to_english(orig_text, source_language)
                result[orig_idx]["text"] = translated

        return result

    except Exception as exc:
        logger.warning("Batch segment translation failed, translating individually: %s", exc)
        result = [dict(seg) for seg in segments]
        for orig_idx, orig_text in non_empty:
            try:
                result[orig_idx]["text"] = translate_to_english(orig_text, source_language)
            except Exception:
                pass  # Keep original text on failure
        return result
