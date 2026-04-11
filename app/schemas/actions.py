from datetime import datetime

from pydantic import BaseModel, Field


class ContactBasicResponse(BaseModel):
    id: str
    name: str
    phone: str | None = None
    email: str | None = None
    whatsapp_number: str | None = None
    notes: str | None = None
    name_aliases: list[str] = Field(default_factory=list)


class ContactCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    whatsapp_number: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=500)
    name_aliases: list[str] = Field(default_factory=list)


class ContactUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    whatsapp_number: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=500)
    name_aliases: list[str] | None = None


class ActionCardResponse(BaseModel):
    id: str
    action_type: str
    status: str
    recipient_name: str
    recipient_phone: str | None = None
    recipient_email: str | None = None
    contact_resolved: bool
    draft_subject: str | None = None
    draft_body: str
    original_transcript_snippet: str | None = None
    confidence_score: float | None = None
    detected_at: datetime
    session_id: str | None = None
    contact: ContactBasicResponse | None = None


class PendingActionsListResponse(BaseModel):
    actions: list[ActionCardResponse]


class PendingActionUpdateRequest(BaseModel):
    status: str = Field(pattern="^(sent|dismissed|edited_sent)$")
    edited_body: str | None = None


class PendingActionDraftEditRequest(BaseModel):
    new_body: str = Field(min_length=1)
    new_subject: str | None = None


class PendingActionAssignContactRequest(BaseModel):
    contact_id: str
