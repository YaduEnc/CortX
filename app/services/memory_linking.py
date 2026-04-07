from __future__ import annotations

import re
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entity import Entity, EntityMention
from app.models.founder import FounderIdeaCluster, FounderIdeaMemory, FounderIdeaStatus
from app.models.memory_link import MemoryLink, MemoryLinkSource, MemoryLinkStatus, MemoryLinkType
from app.utils.time import utc_now


def normalize_memory_link_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


_ALLOWED_ENTITY_LINK_TYPES = {
    MemoryLinkType.person.value: "person",
    MemoryLinkType.project.value: "project",
    MemoryLinkType.place.value: "place",
}


def create_or_reuse_entity_for_link(
    db: Session,
    *,
    user_id: str,
    link_type: str,
    name: str,
) -> Entity:
    entity_type = _ALLOWED_ENTITY_LINK_TYPES[link_type]
    normalized = normalize_memory_link_name(name)
    entity = db.scalar(
        select(Entity).where(
            Entity.user_id == user_id,
            Entity.entity_type == entity_type,
            Entity.normalized_name == normalized,
        )
    )
    now = utc_now()
    if entity:
        entity.last_seen_at = now
        return entity

    entity = Entity(
        user_id=user_id,
        entity_type=entity_type,
        name=name[:255],
        normalized_name=normalized,
        mention_count=0,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(entity)
    db.flush()
    return entity


def create_founder_idea_for_link(
    db: Session,
    *,
    user_id: str,
    title: str,
    summary: str | None = None,
    target_user: str | None = None,
) -> FounderIdeaCluster:
    normalized = normalize_memory_link_name(title)
    idea = db.scalar(
        select(FounderIdeaCluster).where(
            FounderIdeaCluster.user_id == user_id,
            FounderIdeaCluster.normalized_title == normalized,
        )
    )
    now = utc_now()
    if idea:
        idea.last_seen_at = now
        return idea

    idea = FounderIdeaCluster(
        user_id=user_id,
        title=title[:255],
        normalized_title=normalized,
        summary=(summary or None),
        target_user=(target_user or None),
        status=FounderIdeaStatus.emerging.value,
        confidence=None,
        novelty_score=None,
        conviction_score=None,
        mention_count=0,
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(idea)
    db.flush()
    return idea


def upsert_memory_link(
    db: Session,
    *,
    user_id: str,
    session_id: str,
    link_type: str,
    source: str,
    status: str,
    confidence: float | None = None,
    entity_id: str | None = None,
    founder_idea_id: str | None = None,
) -> MemoryLink:
    if (entity_id is None) == (founder_idea_id is None):
        raise ValueError("Exactly one target must be provided")

    query = select(MemoryLink).where(
        MemoryLink.user_id == user_id,
        MemoryLink.session_id == session_id,
        MemoryLink.link_type == link_type,
    )
    if entity_id is not None:
        query = query.where(MemoryLink.entity_id == entity_id)
    else:
        query = query.where(MemoryLink.founder_idea_id == founder_idea_id)

    existing = db.scalar(query)
    now = utc_now()

    if existing:
        if source in {MemoryLinkSource.manual.value, MemoryLinkSource.manual_created.value}:
            existing.source = source
            existing.status = status
            existing.confidence = confidence
            existing.updated_at = now
            return existing

        if existing.status == MemoryLinkStatus.rejected.value:
            return existing
        if existing.source in {MemoryLinkSource.manual.value, MemoryLinkSource.manual_created.value}:
            return existing
        if existing.status == MemoryLinkStatus.confirmed.value:
            return existing
        existing.confidence = max(existing.confidence or 0.0, confidence or 0.0) or None
        existing.updated_at = now
        return existing

    link = MemoryLink(
        user_id=user_id,
        session_id=session_id,
        link_type=link_type,
        entity_id=entity_id,
        founder_idea_id=founder_idea_id,
        source=source,
        status=status,
        confidence=confidence,
        created_at=now,
        updated_at=now,
    )
    db.add(link)
    db.flush()
    return link


def suggest_memory_links_for_session(db: Session, *, user_id: str, session_id: str) -> dict[str, int]:
    created_entities = 0
    created_founder = 0

    entity_rows = db.execute(
        select(Entity.id, Entity.entity_type, func.max(EntityMention.confidence))
        .join(EntityMention, EntityMention.entity_id == Entity.id)
        .where(
            Entity.user_id == user_id,
            EntityMention.session_id == session_id,
            Entity.entity_type.in_(["person", "project", "place"]),
        )
        .group_by(Entity.id, Entity.entity_type)
    ).all()

    for entity_id, entity_type, confidence in entity_rows:
        before_existing = db.scalar(
            select(MemoryLink.id).where(
                MemoryLink.user_id == user_id,
                MemoryLink.session_id == session_id,
                MemoryLink.link_type == entity_type,
                MemoryLink.entity_id == entity_id,
            )
        )
        link = upsert_memory_link(
            db,
            user_id=user_id,
            session_id=session_id,
            link_type=entity_type,
            entity_id=entity_id,
            founder_idea_id=None,
            source=MemoryLinkSource.ai_suggested.value,
            status=MemoryLinkStatus.suggested.value,
            confidence=float(confidence) if confidence is not None else None,
        )
        if before_existing is None and link.source == MemoryLinkSource.ai_suggested.value and link.status == MemoryLinkStatus.suggested.value:
            created_entities += 1

    founder_rows = db.execute(
        select(FounderIdeaCluster.id)
        .join(FounderIdeaMemory, FounderIdeaMemory.idea_cluster_id == FounderIdeaCluster.id)
        .where(
            FounderIdeaCluster.user_id == user_id,
            FounderIdeaMemory.session_id == session_id,
        )
        .group_by(FounderIdeaCluster.id)
    ).all()

    for (idea_id,) in founder_rows:
        before_existing = db.scalar(
            select(MemoryLink.id).where(
                MemoryLink.user_id == user_id,
                MemoryLink.session_id == session_id,
                MemoryLink.link_type == MemoryLinkType.founder_idea.value,
                MemoryLink.founder_idea_id == idea_id,
            )
        )
        link = upsert_memory_link(
            db,
            user_id=user_id,
            session_id=session_id,
            link_type=MemoryLinkType.founder_idea.value,
            entity_id=None,
            founder_idea_id=idea_id,
            source=MemoryLinkSource.ai_suggested.value,
            status=MemoryLinkStatus.suggested.value,
            confidence=0.75,
        )
        if before_existing is None and link.source == MemoryLinkSource.ai_suggested.value and link.status == MemoryLinkStatus.suggested.value:
            created_founder += 1

    db.commit()
    return {
        "entity_links": created_entities,
        "founder_links": created_founder,
    }
