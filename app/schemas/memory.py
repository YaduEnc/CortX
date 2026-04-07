from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class MemoryLinkedEntityResponse(BaseModel):
    entity_id: str
    entity_type: str
    name: str


class MemoryLinkedFounderIdeaResponse(BaseModel):
    idea_id: str
    title: str
    status: str


class MemoryLinkResponse(BaseModel):
    link_id: str
    session_id: str
    link_type: str
    source: str
    status: str
    confidence: float | None
    created_at: datetime
    updated_at: datetime
    entity: MemoryLinkedEntityResponse | None = None
    founder_idea: MemoryLinkedFounderIdeaResponse | None = None


class MemoryLinkCreateRequest(BaseModel):
    link_type: str = Field(pattern="^(person|project|place|founder_idea)$")
    entity_id: str | None = None
    founder_idea_id: str | None = None
    create_name: str | None = Field(default=None, max_length=255)
    create_summary: str | None = Field(default=None, max_length=4000)
    create_target_user: str | None = Field(default=None, max_length=4000)


class MemoryLinkUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(suggested|confirmed|rejected)$")


class LinkTargetSearchEntityResponse(BaseModel):
    entity_id: str
    entity_type: str
    name: str
    mention_count: int


class LinkTargetSearchFounderIdeaResponse(BaseModel):
    idea_id: str
    title: str
    status: str
    mention_count: int


class LinkTargetSearchResponse(BaseModel):
    entities: list[LinkTargetSearchEntityResponse]
    founder_ideas: list[LinkTargetSearchFounderIdeaResponse]


class MemorySearchResultResponse(BaseModel):
    session_id: str
    device_id: str
    device_code: str
    status: str
    total_chunks: int
    started_at: datetime
    finalized_at: datetime | None
    duration_seconds: float | None
    has_audio: bool
    score: float
    snippet: str | None
    match_sources: list[str]
    matched_entities: list[MemoryLinkedEntityResponse]
    matched_founder_ideas: list[MemoryLinkedFounderIdeaResponse]


class MemorySearchResponse(BaseModel):
    query: str | None
    total: int
    limit: int
    offset: int
    results: list[MemorySearchResultResponse]
