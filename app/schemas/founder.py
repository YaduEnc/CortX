from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class FounderIdeaActionResponse(BaseModel):
    action_id: str
    idea_cluster_id: str
    title: str
    details: str | None
    status: str
    priority: int | None
    due_at: datetime | None
    source: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class FounderIdeaMemoryResponse(BaseModel):
    memory_id: str
    session_id: str
    transcript_id: str
    relevance_score: float | None
    role: str
    created_at: datetime


class FounderIdeaClusterResponse(BaseModel):
    idea_id: str
    title: str
    summary: str | None
    problem_statement: str | None
    proposed_solution: str | None
    target_user: str | None
    status: str
    confidence: float | None
    novelty_score: float | None
    conviction_score: float | None
    mention_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime


class FounderIdeaDetailResponse(FounderIdeaClusterResponse):
    memories: list[FounderIdeaMemoryResponse]
    actions: list[FounderIdeaActionResponse]
    linked_signal_count: int


class FounderSignalResponse(BaseModel):
    signal_id: str
    signal_type: str
    title: str
    summary: str | None
    strength: float | None
    session_id: str | None
    transcript_id: str | None
    idea_cluster_id: str | None
    created_at: datetime


class FounderWeeklyMemoResponse(BaseModel):
    memo_id: str | None
    week_start: date
    headline: str
    memo_text: str
    top_ideas: list[dict]
    top_risks: list[str]
    top_actions: list[str]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FounderIdeasListResponse(BaseModel):
    ideas: list[FounderIdeaClusterResponse]
    total: int


class FounderSignalsListResponse(BaseModel):
    signals: list[FounderSignalResponse]
    total: int


class FounderIdeaRefreshResponse(BaseModel):
    idea_id: str
    status: str
    refreshed: bool


class FounderIdeaActionUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|done|dismissed)$")
    due_at: datetime | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
