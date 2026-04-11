from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from app.core.config import get_settings
from app.services.assistant_llm import _clean_json_text, _content_to_text

logger = logging.getLogger(__name__)


INTENT_CLASSIFICATION_PROMPT = """
You are an intent extractor for a personal cognitive assistant.

Analyze the following transcript and extract any communication actions the speaker intends to take.

Return ONLY a valid JSON array. No explanation. No markdown. No preamble.

For each detected intent, return:
{{
  "action_type": "sms" | "whatsapp" | "email" | "iMessage",
  "recipient_name": "exact name mentioned",
  "message_context": "what needs to be communicated - summarized",
  "original_snippet": "exact phrase from transcript that triggered this",
  "confidence": 0.0 to 1.0,
  "preferred_channel": "whatsapp" | "sms" | "email"
}}

Rules:
- Only extract CLEAR outgoing communication intent ("message X", "text X", "email X", "tell X", "let X know", "send X", "I want to message X", "I need to tell X", "remind X", "ask X to")
- Passive mentions ("I talked to Priya") are NOT intents
- If no communication intent exists, return []
- confidence below 0.6 should still be included but flagged
- Infer preferred channel: if person says "WhatsApp", use whatsapp. If says "email", use email. Otherwise default to whatsapp.

Transcript:
{transcript}
""".strip()


DRAFT_GENERATION_PROMPT = """
You are SecondMind, a personal cognitive assistant.
You are drafting a message on behalf of the user based on what they said.

Write a natural, warm, human-sounding message.
- Maximum 3 sentences
- No bullet points, no markdown
- Match the tone: casual for WhatsApp/SMS, slightly more formal for email
- Do not add unnecessary pleasantries unless context warrants it
- Write in first person as the user

Context about what to communicate:
{message_context}

Original quote from user:
"{original_snippet}"

Recipient name: {recipient_name}
Channel: {channel}
{email_subject_instruction}

Return ONLY valid JSON:
{{
  "subject": "email subject line or null",
  "body": "the drafted message"
}}
""".strip()


def _lmstudio_headers() -> dict[str, str]:
    settings = get_settings()
    headers = {"Content-Type": "application/json"}
    if settings.lmstudio_api_key:
        headers["Authorization"] = f"Bearer {settings.lmstudio_api_key}"
    return headers


def _call_lmstudio(messages: list[dict[str, str]], temperature: float = 0.0) -> str:
    settings = get_settings()
    url = settings.lmstudio_base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": settings.lmstudio_model,
        "temperature": temperature,
        "messages": messages,
    }
    response = requests.post(
        url,
        headers=_lmstudio_headers(),
        json=payload,
        timeout=settings.lmstudio_timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LM Studio response missing choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ValueError("LM Studio response missing message")
    content = _content_to_text(message.get("content")).strip()
    if not content:
        raise ValueError("LM Studio response content is empty")
    return content


def _normalize_channel(value: Any) -> str:
    raw = str(value or "").strip()
    lowered = raw.lower()
    if lowered in {"sms", "whatsapp", "email"}:
        return lowered
    if lowered == "imessage":
        return "iMessage"
    return "whatsapp"


def _normalize_intents(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        recipient_name = str(item.get("recipient_name") or "").strip()
        message_context = str(item.get("message_context") or "").strip()
        original_snippet = str(item.get("original_snippet") or "").strip()
        if not recipient_name or not message_context:
            continue
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(confidence, 1.0))
        preferred_channel = _normalize_channel(item.get("preferred_channel"))
        action_type = _normalize_channel(item.get("action_type")) or preferred_channel
        normalized.append(
            {
                "action_type": action_type,
                "recipient_name": recipient_name[:255],
                "message_context": message_context[:2000],
                "original_snippet": original_snippet[:1000] or None,
                "confidence": confidence,
                "preferred_channel": preferred_channel,
            }
        )
    return normalized


_INTENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)\b(?:i want to|i need to|please|can you|could you)?\s*"
        r"(message|text|whatsapp|email|tell|inform|let)\s+"
        r"(?P<recipient>(?:my\s+)?[a-zA-Z][a-zA-Z\s]{0,40}?)\s+"
        r"(?:that|about|to)\s+(?P<context>.+)",
    ),
    re.compile(
        r"(?i)\bremind\s+(?P<recipient>(?:my\s+)?[a-zA-Z][a-zA-Z\s]{0,40}?)\s+"
        r"(?:that|about|to)\s+(?P<context>.+)",
    ),
)


def _normalize_recipient_name(raw: str) -> str:
    recipient = raw.strip().strip(".,!?")
    recipient = re.sub(r"^(my)\s+", "", recipient, flags=re.IGNORECASE)
    words = [word for word in recipient.split() if word]
    if not words:
        return ""
    normalized_words: list[str] = []
    for word in words:
        lowered = word.lower()
        if lowered in {"mom", "mother", "dad", "father", "sister", "brother", "wife", "husband"}:
            normalized_words.append(lowered.capitalize())
        else:
            normalized_words.append(word.capitalize())
    return " ".join(normalized_words)


def _heuristic_detect_intents(transcript: str) -> list[dict[str, Any]]:
    text = transcript.strip()
    if not text:
        return []

    intents: list[dict[str, Any]] = []
    for pattern in _INTENT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        verb = (match.group(1) if match.lastindex and match.lastindex >= 1 else "").lower()
        recipient = _normalize_recipient_name(match.group("recipient"))
        context = match.group("context").strip().strip(" .")
        if not recipient or not context:
            continue

        channel = "email" if "email" in verb else "whatsapp"
        action_type = "email" if channel == "email" else "whatsapp"
        intents.append(
            {
                "action_type": action_type,
                "recipient_name": recipient,
                "message_context": context[:2000],
                "original_snippet": text[:1000],
                "confidence": 0.78,
                "preferred_channel": channel,
            }
        )

    return intents


async def detect_communication_intents(transcript: str) -> list[dict[str, Any]]:
    if not transcript.strip():
        return []

    try:
        content = _call_lmstudio(
            [
                {"role": "system", "content": "Return only strict JSON arrays for communication intent extraction."},
                {"role": "user", "content": INTENT_CLASSIFICATION_PROMPT.format(transcript=transcript.strip())},
            ],
            temperature=0.0,
        )
        parsed = json.loads(_clean_json_text(content))
        normalized = _normalize_intents(parsed)
        if normalized:
            return normalized
        return _heuristic_detect_intents(transcript)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Communication intent detection failed: %s", exc)
        return _heuristic_detect_intents(transcript)


async def draft_message(intent: dict[str, Any]) -> dict[str, str | None]:
    message_context = str(intent.get("message_context") or "").strip()
    recipient_name = str(intent.get("recipient_name") or "").strip()
    original_snippet = str(intent.get("original_snippet") or "").strip()
    channel = _normalize_channel(intent.get("preferred_channel") or intent.get("action_type"))
    if not message_context or not recipient_name:
        return {"subject": None, "body": message_context or ""}

    email_subject_instruction = (
        "Also set a concise email subject line."
        if channel == "email"
        else "Set subject to null."
    )

    try:
        content = _call_lmstudio(
            [
                {"role": "system", "content": "Return only strict JSON objects for drafted messages."},
                {
                    "role": "user",
                    "content": DRAFT_GENERATION_PROMPT.format(
                        message_context=message_context,
                        original_snippet=original_snippet,
                        recipient_name=recipient_name,
                        channel=channel,
                        email_subject_instruction=email_subject_instruction,
                    ),
                },
            ],
            temperature=0.2,
        )
        parsed = json.loads(_clean_json_text(content))
        if not isinstance(parsed, dict):
            raise ValueError("Draft payload is not an object")
        body = str(parsed.get("body") or "").strip()
        subject_raw = parsed.get("subject")
        subject = str(subject_raw).strip() if isinstance(subject_raw, str) and subject_raw.strip() else None
        if not body:
            raise ValueError("Draft body missing")
        return {"subject": subject, "body": body}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Draft generation failed for recipient=%s: %s", recipient_name, exc)
        fallback_subject = f"Message for {recipient_name}" if channel == "email" else None
        return {"subject": fallback_subject, "body": message_context}
