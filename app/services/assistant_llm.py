from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any

import requests

from app.core.config import get_settings


class AssistantLLMError(RuntimeError):
    pass


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


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
                part_text = part.get("text")
                if isinstance(part_text, str):
                    parts.append(part_text)
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts)
    return ""


def _clamp_priority(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, min(parsed, 5))


def _normalize_status(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"open", "done", "dismissed", "snoozed"}:
        return raw
    return "open"


def _normalize_item(raw: dict[str, Any], item_type: str) -> dict[str, Any] | None:
    title = str(raw.get("title") or "").strip()
    if not title:
        return None

    details = str(raw.get("details") or "").strip() or None
    timezone_name = str(raw.get("timezone") or "").strip() or None
    status = _normalize_status(raw.get("status"))

    return {
        "item_type": item_type,
        "title": title[:255],
        "details": details,
        "due_at": _parse_datetime(raw.get("due_at")),
        "timezone": timezone_name,
        "priority": _clamp_priority(raw.get("priority")),
        "status": status,
        "source_segment_start_seconds": float(raw["source_segment_start_seconds"]) if raw.get("source_segment_start_seconds") is not None else None,
        "source_segment_end_seconds": float(raw["source_segment_end_seconds"]) if raw.get("source_segment_end_seconds") is not None else None,
    }


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    intent = str(payload.get("intent") or "").strip() or None
    summary = str(payload.get("summary") or "").strip() or None

    confidence_raw = payload.get("intent_confidence")
    try:
        intent_confidence = float(confidence_raw) if confidence_raw is not None else None
    except (TypeError, ValueError):
        intent_confidence = None
    if intent_confidence is not None:
        intent_confidence = max(0.0, min(intent_confidence, 1.0))

    plan_steps: list[dict[str, Any]] = []
    for step in payload.get("plan_steps") or []:
        if not isinstance(step, dict):
            continue
        normalized = _normalize_item(step, "plan_step")
        if normalized:
            plan_steps.append(normalized)

    tasks: list[dict[str, Any]] = []
    for item in payload.get("tasks") or []:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_item(item, "task")
        if normalized:
            tasks.append(normalized)

    reminders: list[dict[str, Any]] = []
    for item in payload.get("reminders") or []:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_item(item, "reminder")
        if normalized:
            reminders.append(normalized)

    return {
        "intent": intent,
        "intent_confidence": intent_confidence,
        "summary": summary,
        "plan_steps": plan_steps,
        "tasks": tasks,
        "reminders": reminders,
    }


def extract_assistant_payload(transcript_text: str, transcript_language: str | None) -> dict[str, Any]:
    settings = get_settings()
    if not transcript_text.strip():
        raise AssistantLLMError("Transcript text is empty")

    url = settings.lmstudio_base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.lmstudio_api_key:
        headers["Authorization"] = f"Bearer {settings.lmstudio_api_key}"

    system_prompt = (
        "You are an assistant extraction engine. "
        "The transcript input may be in English, Hindi, or Hinglish (Hindi mixed with English). "
        "Your task is to extract actionable intelligence and return it ONLY in English. "
        "Regardless of the input language, the output (intent, summary, titles, and details) MUST be strictly in English. "
        "Return ONLY valid JSON with keys: intent, intent_confidence, summary, plan_steps, tasks, reminders. "
        "Item objects may include: title, details, due_at (ISO8601), timezone, priority(1-5), status(open|done|dismissed|snoozed), "
        "source_segment_start_seconds, source_segment_end_seconds."
    )

    user_prompt = (
        f"Transcript language hint: {transcript_language or 'unknown'}\n"
        "Extract actionable assistant output from this transcript.\n"
        "Transcript:\n"
        f"{transcript_text}"
    )

    request_payload = {
        "model": settings.lmstudio_model,
        "temperature": settings.lmstudio_temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "assistant_extraction",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "intent": {"type": ["string", "null"]},
                        "intent_confidence": {"type": ["number", "null"]},
                        "summary": {"type": ["string", "null"]},
                        "plan_steps": {"type": "array", "items": {"type": "object"}},
                        "tasks": {"type": "array", "items": {"type": "object"}},
                        "reminders": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["intent", "intent_confidence", "summary", "plan_steps", "tasks", "reminders"],
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
        raise AssistantLLMError(f"LM Studio request failed: {exc}") from exc

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
            raise AssistantLLMError(f"LM Studio request failed: {exc}") from exc
        if fallback_response.status_code < 400:
            response = fallback_response
        else:
            raise AssistantLLMError(f"LM Studio HTTP {response.status_code}: {response.text[:500]}")

    try:
        response_json = response.json()
    except ValueError as exc:
        raise AssistantLLMError("LM Studio response is not JSON") from exc

    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AssistantLLMError("LM Studio response missing choices")

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise AssistantLLMError("LM Studio response missing message")

    content_text = _content_to_text(message.get("content"))
    if not content_text.strip():
        raise AssistantLLMError("LM Studio response content is empty")

    cleaned = _clean_json_text(content_text)
    try:
        structured = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AssistantLLMError(f"LM Studio content is not strict JSON: {exc}") from exc

    if not isinstance(structured, dict):
        raise AssistantLLMError("LM Studio JSON payload must be an object")

    normalized = _normalize_payload(structured)
    normalized["raw_json"] = structured
    normalized["model_name"] = str(response_json.get("model") or settings.lmstudio_model)
    return normalized
