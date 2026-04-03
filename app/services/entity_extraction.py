"""
Entity extraction and graph-building service.

After AI extraction completes, this service processes the transcript + AI payload
to identify entities (People, Projects, Topics, Places, Organizations) and
creates/updates Entity records with cross-session linking via EntityMention.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entity import Entity, EntityMention
from app.utils.time import utc_now

logger = logging.getLogger(__name__)


class EntityExtractionError(RuntimeError):
    pass


def _normalize_entity_name(name: str) -> str:
    """Lowercase, strip, collapse whitespace for dedup matching."""
    cleaned = re.sub(r"\s+", " ", name.strip().lower())
    return cleaned


ENTITY_EXTRACTION_SYSTEM_PROMPT = (
    "You are an entity extraction engine. "
    "From the transcript below, extract all named entities. "
    "Return ONLY valid JSON with key 'entities' containing an array of objects. "
    "Each entity object must have: "
    "  name (string, the canonical English name), "
    "  entity_type (one of: person, project, topic, place, organization), "
    "  context (string, a short 1-sentence snippet showing how the entity was mentioned), "
    "  confidence (float 0-1, how confident you are this is a real entity). "
    "Deduplicate entities by name. Merge variations (e.g. 'Mom' and 'Mother' -> 'Mom'). "
    "Output must be in English regardless of transcript language. "
    "If no entities are found, return {\"entities\": []}."
)


def extract_entities_from_transcript(
    transcript_text: str,
    transcript_language: str | None = None,
) -> list[dict[str, Any]]:
    """Call LM Studio to extract entities from a transcript."""
    settings = get_settings()
    if not transcript_text.strip():
        return []

    url = settings.lmstudio_base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.lmstudio_api_key:
        headers["Authorization"] = f"Bearer {settings.lmstudio_api_key}"

    user_prompt = (
        f"Transcript language: {transcript_language or 'unknown'}\n"
        f"Transcript:\n{transcript_text}"
    )

    request_payload = {
        "model": settings.lmstudio_model,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": ENTITY_EXTRACTION_SYSTEM_PROMPT},
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
        raise EntityExtractionError(f"LM Studio entity extraction request failed: {exc}") from exc

    if response.status_code >= 400:
        raise EntityExtractionError(f"LM Studio HTTP {response.status_code}: {response.text[:500]}")

    try:
        response_json = response.json()
    except ValueError as exc:
        raise EntityExtractionError("LM Studio entity response is not JSON") from exc

    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return []

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return []

    content = message.get("content", "")
    if isinstance(content, list):
        content = "\n".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )

    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        content = content.strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Entity extraction returned non-JSON content: %s", content[:200])
        return []

    if not isinstance(parsed, dict):
        return []

    raw_entities = parsed.get("entities", [])
    if not isinstance(raw_entities, list):
        return []

    valid_types = {"person", "project", "topic", "place", "organization"}
    result = []
    for raw in raw_entities:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name or len(name) < 2:
            continue
        entity_type = str(raw.get("entity_type") or "").strip().lower()
        if entity_type not in valid_types:
            entity_type = "topic"

        confidence = None
        try:
            confidence = float(raw.get("confidence", 0.5))
            confidence = max(0.0, min(confidence, 1.0))
        except (TypeError, ValueError):
            confidence = 0.5

        context = str(raw.get("context") or "").strip()[:500] or None

        result.append({
            "name": name[:255],
            "entity_type": entity_type,
            "context": context,
            "confidence": confidence,
        })

    return result


def persist_entities(
    db: Session,
    user_id: str,
    session_id: str,
    extraction_id: str | None,
    entities: list[dict[str, Any]],
) -> int:
    """
    Upsert entities and create mentions for a capture session.
    Returns the number of entity mentions created.
    """
    now = utc_now()
    created = 0

    for entity_data in entities:
        name = entity_data["name"]
        normalized = _normalize_entity_name(name)
        entity_type = entity_data["entity_type"]

        existing = db.scalar(
            select(Entity).where(
                Entity.user_id == user_id,
                Entity.normalized_name == normalized,
                Entity.entity_type == entity_type,
            )
        )

        if existing:
            existing.mention_count = (existing.mention_count or 0) + 1
            existing.last_seen_at = now
            if len(name) > len(existing.name):
                existing.name = name
            entity = existing
        else:
            entity = Entity(
                user_id=user_id,
                entity_type=entity_type,
                name=name,
                normalized_name=normalized,
                mention_count=1,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(entity)
            db.flush()

        already_mentioned = db.scalar(
            select(func.count(EntityMention.id)).where(
                EntityMention.entity_id == entity.id,
                EntityMention.session_id == session_id,
            )
        )
        if already_mentioned and already_mentioned > 0:
            continue

        mention = EntityMention(
            entity_id=entity.id,
            user_id=user_id,
            session_id=session_id,
            extraction_id=extraction_id,
            context_snippet=entity_data.get("context"),
            confidence=entity_data.get("confidence"),
        )
        db.add(mention)
        created += 1

    db.commit()
    return created
