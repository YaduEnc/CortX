from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_app_user
from app.db.session import get_db
from app.models.action import Contact, PendingAction, PendingActionStatus
from app.models.app_user import AppUser
from app.schemas.actions import (
    ActionCardResponse,
    ContactBasicResponse,
    ContactCreateRequest,
    ContactUpdateRequest,
    PendingActionAssignContactRequest,
    PendingActionDraftEditRequest,
    PendingActionUpdateRequest,
    PendingActionsListResponse,
)
from app.schemas.app_user import AppActionStatusResponse
from app.utils.time import utc_now

router = APIRouter(prefix="/app", tags=["app-actions"])


def _contact_to_response(contact: Contact) -> ContactBasicResponse:
    return ContactBasicResponse(
        id=contact.id,
        name=contact.name,
        phone=contact.phone,
        email=contact.email,
        whatsapp_number=contact.whatsapp_number,
        notes=contact.notes,
        name_aliases=list(contact.name_aliases or []),
    )


def _action_to_response(action: PendingAction) -> ActionCardResponse:
    return ActionCardResponse(
        id=action.id,
        action_type=action.action_type,
        status=action.status,
        recipient_name=action.recipient_name,
        recipient_phone=action.recipient_phone,
        recipient_email=action.recipient_email,
        contact_resolved=action.contact_resolved,
        draft_subject=action.draft_subject,
        draft_body=action.draft_body,
        original_transcript_snippet=action.original_transcript_snippet,
        confidence_score=action.confidence_score,
        detected_at=action.detected_at,
        session_id=action.session_id,
        contact=_contact_to_response(action.contact) if action.contact else None,
    )


def _get_action_for_user(db: Session, user_id: str, action_id: str) -> PendingAction:
    action = db.scalar(
        select(PendingAction)
        .options(selectinload(PendingAction.contact))
        .where(PendingAction.id == action_id, PendingAction.user_id == user_id)
    )
    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    return action


def _get_contact_for_user(db: Session, user_id: str, contact_id: str) -> Contact:
    contact = db.scalar(select(Contact).where(Contact.id == contact_id, Contact.user_id == user_id))
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


@router.get("/actions", response_model=PendingActionsListResponse)
def list_pending_actions(
    current_user: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_db),
) -> PendingActionsListResponse:
    actions = db.scalars(
        select(PendingAction)
        .options(selectinload(PendingAction.contact))
        .where(
            PendingAction.user_id == current_user.id,
            PendingAction.status == PendingActionStatus.pending.value,
        )
        .order_by(PendingAction.detected_at.desc())
    ).all()
    return PendingActionsListResponse(actions=[_action_to_response(action) for action in actions])


@router.patch("/actions/{action_id}", response_model=ActionCardResponse)
def update_pending_action(
    action_id: str,
    payload: PendingActionUpdateRequest,
    current_user: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_db),
) -> ActionCardResponse:
    action = _get_action_for_user(db, current_user.id, action_id)
    action.status = payload.status
    if payload.edited_body is not None and payload.edited_body.strip():
        action.draft_body = payload.edited_body.strip()
    action.acted_at = utc_now()
    db.commit()
    db.refresh(action)
    return _action_to_response(action)


@router.post("/actions/{action_id}/edit-draft", response_model=ActionCardResponse)
def edit_pending_action_draft(
    action_id: str,
    payload: PendingActionDraftEditRequest,
    current_user: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_db),
) -> ActionCardResponse:
    action = _get_action_for_user(db, current_user.id, action_id)
    action.draft_body = payload.new_body.strip()
    action.draft_subject = payload.new_subject.strip() if payload.new_subject and payload.new_subject.strip() else None
    db.commit()
    db.refresh(action)
    return _action_to_response(action)


@router.post("/actions/{action_id}/assign-contact", response_model=ActionCardResponse)
def assign_contact_to_action(
    action_id: str,
    payload: PendingActionAssignContactRequest,
    current_user: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_db),
) -> ActionCardResponse:
    action = _get_action_for_user(db, current_user.id, action_id)
    contact = _get_contact_for_user(db, current_user.id, payload.contact_id)
    action.contact_id = contact.id
    action.contact_resolved = True
    action.recipient_name = contact.name
    action.recipient_phone = contact.whatsapp_number or contact.phone
    action.recipient_email = contact.email
    db.commit()
    db.refresh(action)
    return _action_to_response(action)


@router.get("/contacts", response_model=list[ContactBasicResponse])
def list_contacts(
    current_user: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_db),
) -> list[ContactBasicResponse]:
    contacts = db.scalars(
        select(Contact).where(Contact.user_id == current_user.id).order_by(Contact.name.asc())
    ).all()
    return [_contact_to_response(contact) for contact in contacts]


@router.post("/contacts", response_model=ContactBasicResponse, status_code=status.HTTP_201_CREATED)
def create_contact(
    payload: ContactCreateRequest,
    current_user: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_db),
) -> ContactBasicResponse:
    contact = Contact(
        user_id=current_user.id,
        name=payload.name.strip(),
        phone=payload.phone.strip() if payload.phone and payload.phone.strip() else None,
        email=payload.email.strip() if payload.email and payload.email.strip() else None,
        whatsapp_number=payload.whatsapp_number.strip()
        if payload.whatsapp_number and payload.whatsapp_number.strip()
        else None,
        notes=payload.notes.strip() if payload.notes and payload.notes.strip() else None,
        name_aliases=[alias.strip().lower() for alias in payload.name_aliases if alias.strip()],
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return _contact_to_response(contact)


@router.patch("/contacts/{contact_id}", response_model=ContactBasicResponse)
def update_contact(
    contact_id: str,
    payload: ContactUpdateRequest,
    current_user: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_db),
) -> ContactBasicResponse:
    contact = _get_contact_for_user(db, current_user.id, contact_id)
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates:
        contact.name = updates["name"].strip()
    if "phone" in updates:
        contact.phone = updates["phone"].strip() if updates["phone"] and updates["phone"].strip() else None
    if "email" in updates:
        contact.email = updates["email"].strip() if updates["email"] and updates["email"].strip() else None
    if "whatsapp_number" in updates:
        raw = updates["whatsapp_number"]
        contact.whatsapp_number = raw.strip() if raw and raw.strip() else None
    if "notes" in updates:
        contact.notes = updates["notes"].strip() if updates["notes"] and updates["notes"].strip() else None
    if "name_aliases" in updates and updates["name_aliases"] is not None:
        contact.name_aliases = [alias.strip().lower() for alias in updates["name_aliases"] if alias.strip()]
    db.commit()
    db.refresh(contact)
    return _contact_to_response(contact)


@router.delete("/contacts/{contact_id}", response_model=AppActionStatusResponse)
def delete_contact(
    contact_id: str,
    current_user: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_db),
) -> AppActionStatusResponse:
    contact = _get_contact_for_user(db, current_user.id, contact_id)
    db.delete(contact)
    db.commit()
    return AppActionStatusResponse(status="deleted", message="Contact removed")
