from __future__ import annotations

import json
import re
from typing import Any

import requests

from app.core.config import get_settings


class MemoryCardSummaryError(RuntimeError):
    pass


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "for",
    "from",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "we",
    "with",
    "you",
}


def _clean_json_text(text: str) -> str:
    trimmed = text.strip()
    if trimmed.startswith("```"):
        trimmed = re.sub(r"^```(?:json)?\s*", "", trimmed)
        trimmed = re.sub(r"\s*```$", "", trimmed)
    return trimmed.strip()


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


def _normalize_spaces(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _normalize_title(value: str | None) -> str:
    clean = _normalize_spaces(value)
    if not clean:
        return "Untitled Memory"
    words = clean.split()
    title = " ".join(words[:5]).strip(" -,:;.")
    if not title:
        return "Untitled Memory"
    return title[:80]


def _normalize_gist(value: str | None) -> str:
    clean = _normalize_spaces(value)
    if not clean:
        return "Memory summary is not ready yet."
    gist_words = clean.split()
    gist = " ".join(gist_words[:16]).strip()
    if gist and gist[-1] not in ".!?":
        gist += "."
    return gist[:180]


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [part.strip(" \t\r\n-") for part in parts if part and part.strip()]


def build_memory_card_fallback(
    transcript_text: str | None,
    *,
    assistant_summary: str | None = None,
) -> tuple[str, str]:
    source = _normalize_spaces(assistant_summary) or _normalize_spaces(transcript_text)
    if not source:
        return ("Processing Memory", "Transcript and summary are still being prepared.")

    sentences = _split_sentences(source)
    best_sentence = sentences[0] if sentences else source
    gist = _normalize_gist(best_sentence)

    words = re.findall(r"[A-Za-z0-9']+", best_sentence)
    meaningful = [word for word in words if word.lower() not in _STOPWORDS]
    title_words = meaningful[:5] or words[:5]
    title = _normalize_title(" ".join(title_words).title())
    return title, gist


def extract_memory_card_summary(
    *,
    transcript_text: str,
    transcript_language: str | None,
    assistant_summary: str | None,
) -> dict[str, str]:
    settings = get_settings()
    cleaned_transcript = _normalize_spaces(transcript_text)
    if not cleaned_transcript:
        raise MemoryCardSummaryError("Transcript text is empty")

    url = settings.lmstudio_base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.lmstudio_api_key:
        headers["Authorization"] = f"Bearer {settings.lmstudio_api_key}"

    system_prompt = (
        "You create compact memory cards for a voice-notes app. "
        "Return ONLY valid JSON with keys memory_title and memory_gist. "
        "memory_title must be in English, concrete, and at most 5 words. "
        "memory_gist must be in English, one sentence, and explain what the memory is about in 8 to 16 words. "
        "Do not use generic labels like Voice Note, Audio Note, Conversation, or Memory."
    )
    user_prompt = (
        f"Transcript language hint: {transcript_language or 'unknown'}\n"
        f"Existing assistant summary: {assistant_summary or 'none'}\n"
        "Create a compact memory card title and gist for this transcript.\n"
        f"Transcript:\n{cleaned_transcript}"
    )
    request_payload = {
        "model": settings.lmstudio_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "memory_card_summary",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "memory_title": {"type": "string"},
                        "memory_gist": {"type": "string"},
                    },
                    "required": ["memory_title", "memory_gist"],
                },
                "strict": True,
            },
        },
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=request_payload,
            timeout=settings.lmstudio_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise MemoryCardSummaryError(f"LM Studio request failed: {exc}") from exc

    if response.status_code >= 400:
        fallback_payload = dict(request_payload)
        fallback_payload.pop("response_format", None)
        try:
            fallback_response = requests.post(
                url,
                headers=headers,
                json=fallback_payload,
                timeout=settings.lmstudio_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise MemoryCardSummaryError(f"LM Studio request failed: {exc}") from exc
        if fallback_response.status_code < 400:
            response = fallback_response
        else:
            raise MemoryCardSummaryError(
                f"LM Studio HTTP {response.status_code}: {response.text[:500]}"
            )

    try:
        response_json = response.json()
    except ValueError as exc:
        raise MemoryCardSummaryError("LM Studio response is not JSON") from exc

    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise MemoryCardSummaryError("LM Studio response missing choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise MemoryCardSummaryError("LM Studio response missing message")

    content_text = _content_to_text(message.get("content"))
    if not content_text.strip():
        raise MemoryCardSummaryError("LM Studio response content is empty")

    cleaned = _clean_json_text(content_text)
    try:
        structured = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise MemoryCardSummaryError(f"LM Studio content is not strict JSON: {exc}") from exc
    if not isinstance(structured, dict):
        raise MemoryCardSummaryError("LM Studio JSON payload must be an object")

    return {
        "memory_title": _normalize_title(structured.get("memory_title")),
        "memory_gist": _normalize_gist(structured.get("memory_gist")),
    }
