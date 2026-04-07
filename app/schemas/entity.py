from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EntityResponse(BaseModel):
    entity_id: str
    entity_type: str
    name: str
    mention_count: int
    linked_memory_count: int = 0
    first_seen_at: datetime
    last_seen_at: datetime


class EntityMentionResponse(BaseModel):
    mention_id: str
    entity_id: str
    entity_name: str
    entity_type: str
    session_id: str
    context_snippet: str | None
    confidence: float | None
    created_at: datetime


class EntityConnectionResponse(BaseModel):
    source_entity_id: str
    source_name: str
    source_type: str
    target_entity_id: str
    target_name: str
    target_type: str
    shared_session_count: int
    shared_session_ids: list[str]


class IdeaGraphResponse(BaseModel):
    nodes: list[EntityResponse]
    edges: list[EntityConnectionResponse]
    total_entities: int
    total_connections: int
