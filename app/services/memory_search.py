from __future__ import annotations

from datetime import date, datetime, time, timezone
import re
from typing import Any

from sqlalchemy import and_, case, exists, func, literal, or_, select
from sqlalchemy.orm import Session

from app.models.assistant import AIExtraction, AIItem
from app.models.capture import CaptureSession
from app.models.device import Device
from app.models.entity import Entity, EntityMention
from app.models.founder import FounderIdeaCluster, FounderIdeaMemory
from app.models.memory_link import MemoryLink
from app.models.pairing import DeviceUserBinding
from app.models.transcript import Transcript

_SOURCE_ORDER = ["transcript", "summary", "task", "reminder", "entity", "founder_idea"]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _extract_snippet(text: str | None, query: str | None, *, limit: int = 180) -> str | None:
    if not text:
        return None
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return None
    if not query:
        return clean[:limit]
    lowered = clean.lower()
    q = query.lower().strip()
    idx = lowered.find(q)
    if idx < 0:
        return clean[:limit]
    start = max(0, idx - 60)
    end = min(len(clean), idx + len(q) + 100)
    snippet = clean[start:end].strip()
    if start > 0:
        snippet = f"…{snippet}"
    if end < len(clean):
        snippet = f"{snippet}…"
    return snippet


def _match_sources_from_flags(flags: dict[str, bool]) -> list[str]:
    return [source for source in _SOURCE_ORDER if flags.get(source)]


def _bool_expr(expr):
    return case((expr, 1.0), else_=0.0)


def _item_exists_expr(session_id_col, *, item_types: list[str], like_query: str | None = None):
    conditions = [
        AIItem.session_id == session_id_col,
        AIItem.item_type.in_(item_types),
    ]
    if like_query:
        conditions.append(
            or_(
                func.lower(AIItem.title).like(like_query, escape="\\"),
                func.lower(func.coalesce(AIItem.details, "")).like(like_query, escape="\\"),
            )
        )
    return exists(select(AIItem.id).where(*conditions))



def _entity_exists_expr(
    session_id_col,
    *,
    user_id: str,
    like_query: str | None = None,
    entity_type: str | None = None,
):
    explicit_conditions = [
        MemoryLink.user_id == user_id,
        MemoryLink.session_id == session_id_col,
        MemoryLink.status != "rejected",
    ]
    inferred_conditions = [
        Entity.user_id == user_id,
        EntityMention.session_id == session_id_col,
    ]

    if entity_type:
        explicit_conditions.append(Entity.entity_type == entity_type)
        inferred_conditions.append(Entity.entity_type == entity_type)

    if like_query:
        explicit_conditions.append(
            or_(
                func.lower(Entity.name).like(like_query, escape="\\"),
                Entity.normalized_name.like(like_query, escape="\\"),
            )
        )
        inferred_conditions.append(
            or_(
                func.lower(Entity.name).like(like_query, escape="\\"),
                func.lower(func.coalesce(EntityMention.context_snippet, "")).like(like_query, escape="\\"),
            )
        )

    explicit = (
        select(MemoryLink.id)
        .join(Entity, Entity.id == MemoryLink.entity_id)
        .where(*explicit_conditions)
    )
    inferred = (
        select(EntityMention.id)
        .join(Entity, Entity.id == EntityMention.entity_id)
        .where(*inferred_conditions)
    )
    return or_(exists(explicit), exists(inferred))



def _founder_exists_expr(
    session_id_col,
    *,
    user_id: str,
    like_query: str | None = None,
    idea_id: str | None = None,
):
    explicit_conditions = [
        MemoryLink.user_id == user_id,
        MemoryLink.session_id == session_id_col,
        MemoryLink.status != "rejected",
    ]
    inferred_conditions = [
        FounderIdeaCluster.user_id == user_id,
        FounderIdeaMemory.session_id == session_id_col,
    ]

    if idea_id:
        explicit_conditions.append(FounderIdeaCluster.id == idea_id)
        inferred_conditions.append(FounderIdeaCluster.id == idea_id)

    if like_query:
        matcher = or_(
            func.lower(FounderIdeaCluster.title).like(like_query, escape="\\"),
            func.lower(func.coalesce(FounderIdeaCluster.summary, "")).like(like_query, escape="\\"),
            func.lower(func.coalesce(FounderIdeaCluster.target_user, "")).like(like_query, escape="\\"),
        )
        explicit_conditions.append(matcher)
        inferred_conditions.append(matcher)

    explicit = (
        select(MemoryLink.id)
        .join(FounderIdeaCluster, FounderIdeaCluster.id == MemoryLink.founder_idea_id)
        .where(*explicit_conditions)
    )
    inferred = (
        select(FounderIdeaMemory.id)
        .join(FounderIdeaCluster, FounderIdeaCluster.id == FounderIdeaMemory.idea_cluster_id)
        .where(*inferred_conditions)
    )
    return or_(exists(explicit), exists(inferred))



def search_memories(
    db: Session,
    *,
    user_id: str,
    query: str | None,
    limit: int,
    offset: int,
    entity_type: str | None,
    idea_id: str | None,
    has_tasks: bool | None,
    has_reminders: bool | None,
    date_from: date | None,
    date_to: date | None,
) -> dict[str, Any]:
    query_text = (query or "").strip()
    has_query = bool(query_text)
    like_query = f"%{_escape_like(query_text.lower())}%" if has_query else None
    ts_query = func.plainto_tsquery("simple", query_text) if has_query else None

    transcript_rank = literal(0.0)
    summary_rank = literal(0.0)
    if ts_query is not None:
        transcript_rank = func.ts_rank_cd(
            func.to_tsvector("simple", func.coalesce(Transcript.full_text, "")),
            ts_query,
        )
        summary_rank = func.ts_rank_cd(
            func.to_tsvector(
                "simple",
                func.concat(
                    func.coalesce(AIExtraction.summary, ""),
                    literal(" "),
                    func.coalesce(AIExtraction.intent, ""),
                ),
            ),
            ts_query,
        )

    task_presence_expr = _item_exists_expr(CaptureSession.id, item_types=["task", "plan_step"])
    reminder_presence_expr = _item_exists_expr(CaptureSession.id, item_types=["reminder"])
    task_match_expr = _item_exists_expr(CaptureSession.id, item_types=["task", "plan_step"], like_query=like_query) if has_query else literal(False)
    reminder_match_expr = _item_exists_expr(CaptureSession.id, item_types=["reminder"], like_query=like_query) if has_query else literal(False)
    entity_match_expr = _entity_exists_expr(CaptureSession.id, user_id=user_id, like_query=like_query, entity_type=entity_type) if has_query else literal(False)
    founder_match_expr = _founder_exists_expr(CaptureSession.id, user_id=user_id, like_query=like_query, idea_id=idea_id) if has_query else literal(False)
    entity_filter_expr = _entity_exists_expr(CaptureSession.id, user_id=user_id, entity_type=entity_type) if entity_type else None
    founder_filter_expr = _founder_exists_expr(CaptureSession.id, user_id=user_id, idea_id=idea_id) if idea_id else None

    owned_clause = and_(
        DeviceUserBinding.device_id == CaptureSession.device_id,
        DeviceUserBinding.user_id == user_id,
        DeviceUserBinding.is_active.is_(True),
    )

    score_expr = (
        transcript_rank * 4.0
        + summary_rank * 3.0
        + _bool_expr(task_match_expr) * 1.35
        + _bool_expr(reminder_match_expr) * 1.35
        + _bool_expr(entity_match_expr) * 1.0
        + _bool_expr(founder_match_expr) * 1.2
    ).label("score")

    stmt = (
        select(
            CaptureSession.id.label("session_id"),
            CaptureSession.device_id.label("device_id"),
            Device.device_code.label("device_code"),
            CaptureSession.status.label("status"),
            CaptureSession.total_chunks.label("total_chunks"),
            CaptureSession.started_at.label("started_at"),
            CaptureSession.finalized_at.label("finalized_at"),
            CaptureSession.audio_blob_size_bytes.label("audio_blob_size_bytes"),
            CaptureSession.assembled_object_key.label("assembled_object_key"),
            Transcript.duration_seconds.label("duration_seconds"),
            Transcript.full_text.label("transcript_text"),
            AIExtraction.summary.label("summary"),
            transcript_rank.label("transcript_rank"),
            summary_rank.label("summary_rank"),
            task_presence_expr.label("has_tasks"),
            reminder_presence_expr.label("has_reminders"),
            task_match_expr.label("task_match"),
            reminder_match_expr.label("reminder_match"),
            entity_match_expr.label("entity_match"),
            founder_match_expr.label("founder_match"),
            score_expr,
        )
        .join(Device, Device.id == CaptureSession.device_id)
        .join(DeviceUserBinding, owned_clause)
        .outerjoin(Transcript, Transcript.session_id == CaptureSession.id)
        .outerjoin(AIExtraction, AIExtraction.session_id == CaptureSession.id)
    )

    filters = []
    if date_from is not None:
        filters.append(CaptureSession.started_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to is not None:
        filters.append(CaptureSession.started_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    if has_tasks is True:
        filters.append(task_presence_expr)
    if has_tasks is False:
        filters.append(~task_presence_expr)
    if has_reminders is True:
        filters.append(reminder_presence_expr)
    if has_reminders is False:
        filters.append(~reminder_presence_expr)
    if entity_filter_expr is not None:
        filters.append(entity_filter_expr)
    if founder_filter_expr is not None:
        filters.append(founder_filter_expr)
    if has_query:
        filters.append(
            or_(
                transcript_rank > 0,
                summary_rank > 0,
                task_match_expr,
                reminder_match_expr,
                entity_match_expr,
                founder_match_expr,
            )
        )

    if filters:
        stmt = stmt.where(*filters)

    ranked = stmt.subquery()
    total = db.scalar(select(func.count()).select_from(ranked)) or 0

    rows = db.execute(
        select(ranked)
        .order_by(ranked.c.score.desc(), ranked.c.started_at.desc())
        .offset(offset)
        .limit(limit)
    ).mappings().all()

    results = []
    for row in rows:
        session_id = row["session_id"]
        matched_entities = _load_matched_entities(
            db,
            user_id=user_id,
            session_id=session_id,
            query=query_text or None,
            entity_type=entity_type,
        )
        matched_founder_ideas = _load_matched_founder_ideas(
            db,
            user_id=user_id,
            session_id=session_id,
            query=query_text or None,
            idea_id=idea_id,
        )
        flags = {
            "transcript": bool(has_query and (row["transcript_rank"] or 0) > 0),
            "summary": bool(has_query and (row["summary_rank"] or 0) > 0),
            "task": bool(row["task_match"] if has_query else (has_tasks is True and row["has_tasks"])),
            "reminder": bool(row["reminder_match"] if has_query else (has_reminders is True and row["has_reminders"])),
            "entity": bool(matched_entities),
            "founder_idea": bool(matched_founder_ideas),
        }
        snippet = _best_snippet(
            transcript_text=row.get("transcript_text"),
            summary=row.get("summary"),
            query=query_text or None,
            task_snippet=_load_matching_item_text(db, session_id=session_id, item_types=["task", "plan_step"], query=query_text or None),
            reminder_snippet=_load_matching_item_text(db, session_id=session_id, item_types=["reminder"], query=query_text or None),
            entity_snippet=_load_matching_entity_context(db, user_id=user_id, session_id=session_id, query=query_text or None),
            founder_snippet=_load_matching_founder_text(db, user_id=user_id, session_id=session_id, query=query_text or None, idea_id=idea_id),
            flags=flags,
        )
        results.append(
            {
                "session_id": session_id,
                "device_id": row["device_id"],
                "device_code": row["device_code"],
                "status": row["status"],
                "total_chunks": row["total_chunks"],
                "started_at": row["started_at"],
                "finalized_at": row["finalized_at"],
                "duration_seconds": row["duration_seconds"],
                "has_audio": bool((row["audio_blob_size_bytes"] or 0) > 0 or row["assembled_object_key"]),
                "score": float(row["score"] or 0.0),
                "snippet": snippet,
                "match_sources": _match_sources_from_flags(flags),
                "matched_entities": matched_entities,
                "matched_founder_ideas": matched_founder_ideas,
            }
        )

    return {"total": int(total), "results": results}



def _load_matching_item_text(db: Session, *, session_id: str, item_types: list[str], query: str | None) -> str | None:
    stmt = select(AIItem.title, AIItem.details).where(AIItem.session_id == session_id, AIItem.item_type.in_(item_types))
    if query:
        like_query = f"%{_escape_like(query.lower())}%"
        stmt = stmt.where(
            or_(
                func.lower(AIItem.title).like(like_query, escape="\\"),
                func.lower(func.coalesce(AIItem.details, "")).like(like_query, escape="\\"),
            )
        )
    row = db.execute(stmt.order_by(AIItem.created_at.desc()).limit(1)).first()
    if not row:
        return None
    return row[1] or row[0]



def _load_matching_entity_context(db: Session, *, user_id: str, session_id: str, query: str | None) -> str | None:
    stmt = (
        select(EntityMention.context_snippet, Entity.name)
        .join(Entity, Entity.id == EntityMention.entity_id)
        .where(Entity.user_id == user_id, EntityMention.session_id == session_id)
    )
    if query:
        like_query = f"%{_escape_like(query.lower())}%"
        stmt = stmt.where(
            or_(
                func.lower(Entity.name).like(like_query, escape="\\"),
                func.lower(func.coalesce(EntityMention.context_snippet, "")).like(like_query, escape="\\"),
            )
        )
    row = db.execute(stmt.order_by(EntityMention.created_at.desc()).limit(1)).first()
    if not row:
        return None
    return row[0] or row[1]



def _load_matching_founder_text(db: Session, *, user_id: str, session_id: str, query: str | None, idea_id: str | None) -> str | None:
    stmt = (
        select(FounderIdeaCluster.summary, FounderIdeaCluster.title)
        .join(FounderIdeaMemory, FounderIdeaMemory.idea_cluster_id == FounderIdeaCluster.id)
        .where(FounderIdeaCluster.user_id == user_id, FounderIdeaMemory.session_id == session_id)
    )
    if idea_id:
        stmt = stmt.where(FounderIdeaCluster.id == idea_id)
    if query:
        like_query = f"%{_escape_like(query.lower())}%"
        stmt = stmt.where(
            or_(
                func.lower(FounderIdeaCluster.title).like(like_query, escape="\\"),
                func.lower(func.coalesce(FounderIdeaCluster.summary, "")).like(like_query, escape="\\"),
                func.lower(func.coalesce(FounderIdeaCluster.target_user, "")).like(like_query, escape="\\"),
            )
        )
    row = db.execute(stmt.limit(1)).first()
    if not row:
        return None
    return row[0] or row[1]



def _best_snippet(
    *,
    transcript_text: str | None,
    summary: str | None,
    query: str | None,
    task_snippet: str | None,
    reminder_snippet: str | None,
    entity_snippet: str | None,
    founder_snippet: str | None,
    flags: dict[str, bool],
) -> str | None:
    if flags.get("transcript"):
        return _extract_snippet(transcript_text, query)
    if flags.get("summary"):
        return _extract_snippet(summary, query)
    if flags.get("task"):
        return _extract_snippet(task_snippet, query)
    if flags.get("reminder"):
        return _extract_snippet(reminder_snippet, query)
    if flags.get("entity"):
        return _extract_snippet(entity_snippet, query)
    if flags.get("founder_idea"):
        return _extract_snippet(founder_snippet, query)
    return _extract_snippet(summary or transcript_text, query)



def _load_matched_entities(
    db: Session,
    *,
    user_id: str,
    session_id: str,
    query: str | None,
    entity_type: str | None,
) -> list[dict[str, str]]:
    like_query = f"%{_escape_like(query.lower())}%" if query else None
    explicit_stmt = (
        select(Entity.id, Entity.entity_type, Entity.name)
        .join(MemoryLink, MemoryLink.entity_id == Entity.id)
        .where(
            MemoryLink.user_id == user_id,
            MemoryLink.session_id == session_id,
            MemoryLink.status != "rejected",
        )
    )
    if entity_type:
        explicit_stmt = explicit_stmt.where(Entity.entity_type == entity_type)
    if like_query:
        explicit_stmt = explicit_stmt.where(
            or_(
                func.lower(Entity.name).like(like_query, escape="\\"),
                Entity.normalized_name.like(like_query, escape="\\"),
            )
        )
    explicit_rows = db.execute(explicit_stmt.order_by(Entity.mention_count.desc(), Entity.name.asc()).limit(3)).all()

    seen = {row[0] for row in explicit_rows}
    inferred_stmt = (
        select(Entity.id, Entity.entity_type, Entity.name)
        .join(EntityMention, EntityMention.entity_id == Entity.id)
        .where(Entity.user_id == user_id, EntityMention.session_id == session_id)
    )
    if entity_type:
        inferred_stmt = inferred_stmt.where(Entity.entity_type == entity_type)
    if like_query:
        inferred_stmt = inferred_stmt.where(
            or_(
                func.lower(Entity.name).like(like_query, escape="\\"),
                func.lower(func.coalesce(EntityMention.context_snippet, "")).like(like_query, escape="\\"),
            )
        )
    inferred_rows = db.execute(inferred_stmt.order_by(Entity.mention_count.desc(), Entity.name.asc()).limit(6)).all()

    items = [{"entity_id": row[0], "entity_type": row[1], "name": row[2]} for row in explicit_rows]
    for row in inferred_rows:
        if row[0] in seen:
            continue
        items.append({"entity_id": row[0], "entity_type": row[1], "name": row[2]})
        seen.add(row[0])
        if len(items) >= 3:
            break
    return items



def _load_matched_founder_ideas(
    db: Session,
    *,
    user_id: str,
    session_id: str,
    query: str | None,
    idea_id: str | None,
) -> list[dict[str, str]]:
    like_query = f"%{_escape_like(query.lower())}%" if query else None
    explicit_stmt = (
        select(FounderIdeaCluster.id, FounderIdeaCluster.title, FounderIdeaCluster.status)
        .join(MemoryLink, MemoryLink.founder_idea_id == FounderIdeaCluster.id)
        .where(
            MemoryLink.user_id == user_id,
            MemoryLink.session_id == session_id,
            MemoryLink.status != "rejected",
        )
    )
    if idea_id:
        explicit_stmt = explicit_stmt.where(FounderIdeaCluster.id == idea_id)
    if like_query:
        explicit_stmt = explicit_stmt.where(
            or_(
                func.lower(FounderIdeaCluster.title).like(like_query, escape="\\"),
                func.lower(func.coalesce(FounderIdeaCluster.summary, "")).like(like_query, escape="\\"),
                func.lower(func.coalesce(FounderIdeaCluster.target_user, "")).like(like_query, escape="\\"),
            )
        )
    explicit_rows = db.execute(explicit_stmt.limit(3)).all()
    seen = {row[0] for row in explicit_rows}

    inferred_stmt = (
        select(FounderIdeaCluster.id, FounderIdeaCluster.title, FounderIdeaCluster.status)
        .join(FounderIdeaMemory, FounderIdeaMemory.idea_cluster_id == FounderIdeaCluster.id)
        .where(FounderIdeaCluster.user_id == user_id, FounderIdeaMemory.session_id == session_id)
    )
    if idea_id:
        inferred_stmt = inferred_stmt.where(FounderIdeaCluster.id == idea_id)
    if like_query:
        inferred_stmt = inferred_stmt.where(
            or_(
                func.lower(FounderIdeaCluster.title).like(like_query, escape="\\"),
                func.lower(func.coalesce(FounderIdeaCluster.summary, "")).like(like_query, escape="\\"),
                func.lower(func.coalesce(FounderIdeaCluster.target_user, "")).like(like_query, escape="\\"),
            )
        )
    inferred_rows = db.execute(inferred_stmt.limit(6)).all()

    items = [{"idea_id": row[0], "title": row[1], "status": row[2]} for row in explicit_rows]
    for row in inferred_rows:
        if row[0] in seen:
            continue
        items.append({"idea_id": row[0], "title": row[1], "status": row[2]})
        seen.add(row[0])
        if len(items) >= 3:
            break
    return items
