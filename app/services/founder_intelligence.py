from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import logging
import re
from typing import Any

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.assistant import AIExtraction
from app.models.entity import Entity, EntityMention
from app.models.founder import (
    FounderIdeaAction,
    FounderIdeaActionStatus,
    FounderIdeaCluster,
    FounderIdeaMemory,
    FounderIdeaMemoryRole,
    FounderIdeaStatus,
    FounderSignal,
    FounderSignalType,
    WeeklyFounderMemo,
)
from app.models.transcript import Transcript
from app.utils.time import utc_now

logger = logging.getLogger(__name__)


class FounderIntelligenceError(RuntimeError):
    pass


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _strip_code_fence(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _safe_float(value: Any, *, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(number, 1.0))


def _safe_int(value: Any, *, default: int | None = None, minimum: int | None = None, maximum: int | None = None) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _safe_text(value: Any, *, max_len: int = 4000) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


def _normalize_idea_status(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    allowed = {status.value for status in FounderIdeaStatus}
    return candidate if candidate in allowed else FounderIdeaStatus.emerging.value


def _normalize_memory_role(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    allowed = {role.value for role in FounderIdeaMemoryRole}
    return candidate if candidate in allowed else FounderIdeaMemoryRole.evidence.value


def _normalize_signal_type(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    allowed = {signal.value for signal in FounderSignalType}
    return candidate if candidate in allowed else FounderSignalType.opportunity.value


def _normalize_action_status(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    allowed = {status.value for status in FounderIdeaActionStatus}
    return candidate if candidate in allowed else FounderIdeaActionStatus.open.value


def _parse_due_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _week_start_for(dt: datetime) -> date:
    normalized = dt.astimezone(timezone.utc).date()
    return normalized - timedelta(days=normalized.weekday())


def _existing_ideas_context(db: Session, user_id: str, limit: int = 8) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(FounderIdeaCluster)
        .where(FounderIdeaCluster.user_id == user_id)
        .order_by(FounderIdeaCluster.last_seen_at.desc(), FounderIdeaCluster.updated_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "idea_id": row.id,
            "title": row.title,
            "summary": row.summary,
            "status": row.status,
            "mention_count": row.mention_count,
            "last_seen_at": row.last_seen_at.isoformat(),
        }
        for row in rows
    ]


def _current_entities_context(db: Session, session_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Entity.id, Entity.name, Entity.entity_type, Entity.mention_count)
        .join(EntityMention, EntityMention.entity_id == Entity.id)
        .where(EntityMention.session_id == session_id)
        .order_by(Entity.mention_count.desc(), Entity.name.asc())
        .limit(12)
    ).all()
    return [
        {
            "entity_id": entity_id,
            "name": name,
            "entity_type": entity_type,
            "mention_count": mention_count,
        }
        for entity_id, name, entity_type, mention_count in rows
    ]


FOUNDER_SYSTEM_PROMPT = """
You are a founder-intelligence extraction engine for a long-term memory product.
You analyze one new transcript against the founder's recent idea history.

Return ONLY strict JSON.
No markdown. No explanation. No prose outside the JSON object.

JSON schema:
{
  "idea": {
    "matched_idea_cluster_id": "string or null",
    "create_new": true,
    "title": "string or null",
    "summary": "string or null",
    "problem_statement": "string or null",
    "proposed_solution": "string or null",
    "target_user": "string or null",
    "status": "emerging|active|validating|paused|dropped",
    "confidence": 0.0,
    "novelty_score": 0.0,
    "conviction_score": 0.0,
    "relevance_score": 0.0,
    "memory_role": "origin|evidence|refinement|contradiction|action"
  },
  "signals": [
    {
      "signal_type": "pain_point|obsession|contradiction|opportunity|market_signal",
      "title": "string",
      "summary": "string or null",
      "strength": 0.0
    }
  ],
  "actions": [
    {
      "title": "string",
      "details": "string or null",
      "priority": 1,
      "status": "open|done|dismissed",
      "due_at": "ISO-8601 datetime string or null"
    }
  ],
  "weekly_memo": {
    "headline": "string or null",
    "memo_text": "string or null",
    "top_risks": ["string"],
    "top_actions": ["string"]
  }
}

Rules:
- If the transcript has no startup/founder/product relevance, set idea.title to null and signals to [] unless there is still a clear founder signal.
- Match to an existing idea only if the overlap is strong.
- Create a new idea only when the founder is expressing a distinct opportunity, product direction, or recurring problem worth tracking.
- Be evidence-based, concise, and non-generic.
""".strip()


def extract_founder_payload(
    *,
    transcript_text: str,
    transcript_language: str | None,
    existing_ideas: list[dict[str, Any]],
    current_entities: list[dict[str, Any]],
) -> dict[str, Any]:
    settings = get_settings()
    if not transcript_text.strip():
        raise FounderIntelligenceError("Transcript text is empty")

    url = settings.lmstudio_base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.lmstudio_api_key:
        headers["Authorization"] = f"Bearer {settings.lmstudio_api_key}"

    user_prompt = json.dumps(
        {
            "transcript_language": transcript_language or "unknown",
            "existing_ideas": existing_ideas,
            "current_entities": current_entities,
            "transcript_text": transcript_text,
        },
        ensure_ascii=False,
    )

    request_payload = {
        "model": settings.lmstudio_model,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": FOUNDER_SYSTEM_PROMPT},
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
        raise FounderIntelligenceError(f"LM Studio founder request failed: {exc}") from exc

    if response.status_code >= 400:
        raise FounderIntelligenceError(f"LM Studio founder HTTP {response.status_code}: {response.text[:500]}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise FounderIntelligenceError("LM Studio founder response is not JSON") from exc

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise FounderIntelligenceError("LM Studio founder response missing choices")

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise FounderIntelligenceError("LM Studio founder response missing message")

    content = message.get("content", "")
    if isinstance(content, list):
        content = "\n".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )

    content = _strip_code_fence(str(content))
    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise FounderIntelligenceError(f"Founder response is not valid JSON: {content[:220]}") from exc

    if not isinstance(result, dict):
        raise FounderIntelligenceError("Founder response root must be an object")
    return result


def _upsert_idea_cluster(
    db: Session,
    *,
    user_id: str,
    session_id: str,
    transcript_id: str,
    idea_payload: dict[str, Any],
    existing_ideas_by_id: dict[str, FounderIdeaCluster],
) -> FounderIdeaCluster | None:
    title = _safe_text(idea_payload.get("title"), max_len=255)
    matched_id = _safe_text(idea_payload.get("matched_idea_cluster_id"), max_len=64)
    create_new = bool(idea_payload.get("create_new"))

    idea: FounderIdeaCluster | None = None
    if matched_id and matched_id in existing_ideas_by_id:
        idea = existing_ideas_by_id[matched_id]
    elif title:
        normalized_title = _normalize_name(title)
        idea = db.scalar(
            select(FounderIdeaCluster).where(
                FounderIdeaCluster.user_id == user_id,
                FounderIdeaCluster.normalized_title == normalized_title,
            )
        )

    if idea is None and not create_new and not title:
        return None

    now = utc_now()
    if idea is None:
        if not title:
            return None
        idea = FounderIdeaCluster(
            user_id=user_id,
            title=title,
            normalized_title=_normalize_name(title),
            mention_count=0,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(idea)
        db.flush()

    if title:
        idea.title = title
        idea.normalized_title = _normalize_name(title)
    idea.summary = _safe_text(idea_payload.get("summary")) or idea.summary
    idea.problem_statement = _safe_text(idea_payload.get("problem_statement")) or idea.problem_statement
    idea.proposed_solution = _safe_text(idea_payload.get("proposed_solution")) or idea.proposed_solution
    idea.target_user = _safe_text(idea_payload.get("target_user")) or idea.target_user
    idea.status = _normalize_idea_status(idea_payload.get("status"))
    idea.confidence = _safe_float(idea_payload.get("confidence"), default=idea.confidence)
    idea.novelty_score = _safe_float(idea_payload.get("novelty_score"), default=idea.novelty_score)
    idea.conviction_score = _safe_float(idea_payload.get("conviction_score"), default=idea.conviction_score)
    idea.last_seen_at = now
    idea.mention_count = max(1, int(idea.mention_count or 0))

    existing_memory = db.scalar(
        select(FounderIdeaMemory).where(
            FounderIdeaMemory.idea_cluster_id == idea.id,
            FounderIdeaMemory.session_id == session_id,
        )
    )
    if existing_memory is None:
        db.add(
            FounderIdeaMemory(
                idea_cluster_id=idea.id,
                user_id=user_id,
                session_id=session_id,
                transcript_id=transcript_id,
                relevance_score=_safe_float(idea_payload.get("relevance_score")),
                role=_normalize_memory_role(idea_payload.get("memory_role")),
            )
        )
        idea.mention_count = int(idea.mention_count or 0) + 1

    return idea


def _upsert_actions(
    db: Session,
    *,
    user_id: str,
    idea: FounderIdeaCluster | None,
    actions_payload: Any,
) -> None:
    if idea is None or not isinstance(actions_payload, list):
        return

    for raw_action in actions_payload:
        if not isinstance(raw_action, dict):
            continue
        title = _safe_text(raw_action.get("title"), max_len=255)
        if not title:
            continue
        existing = db.scalar(
            select(FounderIdeaAction).where(
                FounderIdeaAction.idea_cluster_id == idea.id,
                FounderIdeaAction.status == FounderIdeaActionStatus.open.value,
                func.lower(FounderIdeaAction.title) == title.lower(),
            )
        )
        if existing:
            existing.details = _safe_text(raw_action.get("details")) or existing.details
            existing.priority = _safe_int(raw_action.get("priority"), default=existing.priority, minimum=1, maximum=5)
            existing.due_at = _parse_due_at(raw_action.get("due_at")) or existing.due_at
            continue

        db.add(
            FounderIdeaAction(
                idea_cluster_id=idea.id,
                user_id=user_id,
                title=title,
                details=_safe_text(raw_action.get("details")),
                status=_normalize_action_status(raw_action.get("status")),
                priority=_safe_int(raw_action.get("priority"), minimum=1, maximum=5),
                due_at=_parse_due_at(raw_action.get("due_at")),
                source="founder_ai",
                completed_at=utc_now() if _normalize_action_status(raw_action.get("status")) == FounderIdeaActionStatus.done.value else None,
            )
        )


def _persist_signals(
    db: Session,
    *,
    user_id: str,
    session_id: str,
    transcript_id: str,
    idea: FounderIdeaCluster | None,
    signals_payload: Any,
) -> None:
    if not isinstance(signals_payload, list):
        return

    for raw_signal in signals_payload:
        if not isinstance(raw_signal, dict):
            continue
        title = _safe_text(raw_signal.get("title"), max_len=255)
        if not title:
            continue
        db.add(
            FounderSignal(
                user_id=user_id,
                idea_cluster_id=idea.id if idea else None,
                session_id=session_id,
                transcript_id=transcript_id,
                signal_type=_normalize_signal_type(raw_signal.get("signal_type")),
                title=title,
                summary=_safe_text(raw_signal.get("summary")),
                strength=_safe_float(raw_signal.get("strength")),
            )
        )


def _build_weekly_memo_fallback(
    idea: FounderIdeaCluster | None,
    signals_payload: Any,
    actions_payload: Any,
) -> dict[str, Any]:
    signal_titles = [
        _safe_text(item.get("title"), max_len=200)
        for item in signals_payload
        if isinstance(item, dict) and _safe_text(item.get("title"), max_len=200)
    ]
    action_titles = [
        _safe_text(item.get("title"), max_len=200)
        for item in actions_payload
        if isinstance(item, dict) and _safe_text(item.get("title"), max_len=200)
    ]
    return {
        "headline": idea.title if idea else "Founder signals updated",
        "memo_text": idea.summary if idea and idea.summary else "New founder signals were captured from recent memories.",
        "top_risks": signal_titles[:3],
        "top_actions": action_titles[:3],
    }


def _upsert_weekly_memo(
    db: Session,
    *,
    user_id: str,
    session_started_at: datetime,
    idea: FounderIdeaCluster | None,
    weekly_memo_payload: Any,
    signals_payload: Any,
    actions_payload: Any,
) -> None:
    week_start = _week_start_for(session_started_at)
    memo = db.scalar(
        select(WeeklyFounderMemo).where(
            WeeklyFounderMemo.user_id == user_id,
            WeeklyFounderMemo.week_start == week_start,
        )
    )
    if memo is None:
        memo = WeeklyFounderMemo(user_id=user_id, week_start=week_start)
        db.add(memo)

    payload = weekly_memo_payload if isinstance(weekly_memo_payload, dict) else {}
    fallback = _build_weekly_memo_fallback(idea, signals_payload, actions_payload)

    top_ideas_json = []
    if idea is not None:
        top_ideas_json.append(
            {
                "idea_id": idea.id,
                "title": idea.title,
                "status": idea.status,
                "confidence": idea.confidence,
                "conviction_score": idea.conviction_score,
            }
        )

    memo.headline = _safe_text(payload.get("headline")) or fallback["headline"]
    memo.memo_text = _safe_text(payload.get("memo_text")) or fallback["memo_text"]
    memo.top_ideas_json = top_ideas_json
    memo.top_risks_json = [
        text for text in (payload.get("top_risks") if isinstance(payload.get("top_risks"), list) else fallback["top_risks"]) if _safe_text(text, max_len=300)
    ][:5]
    memo.top_actions_json = [
        text for text in (payload.get("top_actions") if isinstance(payload.get("top_actions"), list) else fallback["top_actions"]) if _safe_text(text, max_len=300)
    ][:5]


def process_founder_intelligence(db: Session, session_id: str) -> dict[str, Any]:
    transcript = db.scalar(
        select(Transcript).where(Transcript.session_id == session_id)
    )
    if transcript is None:
        raise FounderIntelligenceError("Transcript not ready")

    extraction = db.scalar(select(AIExtraction).where(AIExtraction.transcript_id == transcript.id))
    session = transcript.session
    if session is None:
        raise FounderIntelligenceError("Capture session not found")

    binding_user_id = db.scalar(
        select(Entity.user_id)
        .join(EntityMention, EntityMention.entity_id == Entity.id)
        .where(EntityMention.session_id == session_id)
        .limit(1)
    )
    user_id = extraction.user_id if extraction else binding_user_id
    if not user_id:
        raise FounderIntelligenceError("User context missing for founder extraction")

    existing_ideas = _existing_ideas_context(db, user_id=user_id)
    entities = _current_entities_context(db, session_id=session_id)
    payload = extract_founder_payload(
        transcript_text=transcript.full_text,
        transcript_language=transcript.language,
        existing_ideas=existing_ideas,
        current_entities=entities,
    )

    idea_payload = payload.get("idea") if isinstance(payload.get("idea"), dict) else {}
    signals_payload = payload.get("signals") if isinstance(payload.get("signals"), list) else []
    actions_payload = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    weekly_memo_payload = payload.get("weekly_memo") if isinstance(payload.get("weekly_memo"), dict) else {}

    existing_ideas_by_id = {
        idea.id: idea
        for idea in db.scalars(select(FounderIdeaCluster).where(FounderIdeaCluster.user_id == user_id)).all()
    }
    idea = _upsert_idea_cluster(
        db,
        user_id=user_id,
        session_id=session_id,
        transcript_id=transcript.id,
        idea_payload=idea_payload,
        existing_ideas_by_id=existing_ideas_by_id,
    )
    _upsert_actions(db, user_id=user_id, idea=idea, actions_payload=actions_payload)
    _persist_signals(
        db,
        user_id=user_id,
        session_id=session_id,
        transcript_id=transcript.id,
        idea=idea,
        signals_payload=signals_payload,
    )
    _upsert_weekly_memo(
        db,
        user_id=user_id,
        session_started_at=session.started_at,
        idea=idea,
        weekly_memo_payload=weekly_memo_payload,
        signals_payload=signals_payload,
        actions_payload=actions_payload,
    )
    db.commit()

    return {
        "idea_id": idea.id if idea else None,
        "signal_count": len(signals_payload),
        "action_count": len(actions_payload),
    }
