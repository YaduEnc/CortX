import asyncio
from datetime import date, datetime, time, timedelta, timezone
import os
import secrets
import shutil
import tempfile
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, File, Header, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_app_user
from app.core.config import get_settings
from app.core.security import create_app_access_token, hash_pair_token, hash_secret, verify_secret
from app.db.session import get_db
from app.models.assistant import AIExtraction, AIItem, AIItemStatus
from app.models.capture import CaptureSession, SessionStatus
from app.models.app_user import AppUser
from app.models.device import Device
from app.models.founder import FounderIdeaAction, FounderIdeaActionStatus, FounderIdeaCluster, FounderIdeaMemory, FounderSignal, WeeklyFounderMemo
from app.models.memory_link import MemoryLink, MemoryLinkSource, MemoryLinkStatus, MemoryLinkType
from app.models.pairing import DeviceUserBinding, PairingSession
from app.models.password_reset import AppPasswordResetToken
from app.models.user_preferences import AppUserPreferences
from app.models.transcript import Transcript
from app.schemas.assistant import (
    AppAssistantItemResponse,
    AppAssistantItemUpdateRequest,
    AppCaptureAIExtractionResponse,
    AppCaptureAIReprocessResponse,
    AppCaptureAIResponse,
)
from app.services.network_profiles import NETWORK_PROFILE_TTL_SECONDS, queue_network_profile
from app.services.assistant_pipeline import AssistantPipelineError, prepare_extraction_record
from app.services.storage import get_storage
from app.schemas.app_user import (
    AppActionStatusResponse,
    AppDailySummaryDeviceBreakdown,
    AppDailySummaryFocusItem,
    AppDailySummaryMetrics,
    AppDailySummaryResponse,
    AppCaptureListItemResponse,
    AppCaptureUploadResponse,
    AppMeResponse,
    AppMeUpdateRequest,
    AppUserPreferencesResponse,
    AppUserPreferencesUpdateRequest,
    AppDeviceUpdateRequest,
    AppCaptureTranscriptResponse,
    AppAuthRequest,
    AppDeleteAccountRequest,
    AppForgotPasswordConfirmRequest,
    AppForgotPasswordRequest,
    AppForgotPasswordRequestResponse,
    AppRegisterRequest,
    AppTokenResponse,
    PairedDeviceResponse,
)
from app.schemas.network import AppQueueNetworkProfileRequest, AppQueueNetworkProfileResponse
from app.schemas.entity import (
    EntityConnectionResponse,
    EntityMentionResponse,
    EntityResponse,
    IdeaGraphResponse,
)
from app.schemas.founder import (
    FounderIdeaActionResponse,
    FounderIdeaActionUpdateRequest,
    FounderIdeaClusterResponse,
    FounderIdeaDetailResponse,
    FounderSignalResponse,
    FounderSignalsListResponse,
    FounderWeeklyMemoResponse,
    FounderIdeasListResponse,
)
from app.schemas.memory import (
    LinkTargetSearchEntityResponse,
    LinkTargetSearchFounderIdeaResponse,
    LinkTargetSearchResponse,
    MemoryLinkCreateRequest,
    MemoryLinkResponse,
    MemoryLinkUpdateRequest,
    MemoryLinkedEntityResponse,
    MemoryLinkedFounderIdeaResponse,
    MemorySearchResponse,
    MemorySearchResultResponse,
)
from app.models.entity import Entity, EntityMention
from app.services.memory_card_summary import build_memory_card_fallback
from app.services.memory_linking import create_founder_idea_for_link, create_or_reuse_entity_for_link, upsert_memory_link
from app.services.memory_search import search_memories
from app.services.embeddings import EmbeddingServiceError
from app.services.semantic_search import query_memories_semantically
from app.services.transcriber import get_transcriber
from app.services.tts_service import TTSServiceError, get_tts_service
from app.services.voice_answer import refine_spoken_answer
from app.schemas.memory import AppMemoryQueryRequest, AppMemoryQueryResponse
from app.utils.time import utc_now
from app.workers.celery_app import celery_app
from fastapi.responses import StreamingResponse
import io

router = APIRouter(prefix="/app", tags=["app"])


def _device_status(last_seen_at: datetime | None, now: datetime) -> str:
    if last_seen_at is None:
        return "offline"
    age = now - last_seen_at
    if age <= timedelta(minutes=2):
        return "online"
    if age <= timedelta(minutes=30):
        return "recently_active"
    return "offline"


def _get_or_create_preferences(db: Session, user_id: str) -> AppUserPreferences:
    prefs = db.scalar(select(AppUserPreferences).where(AppUserPreferences.user_id == user_id))
    if prefs:
        return prefs
    prefs = AppUserPreferences(user_id=user_id)
    db.add(prefs)
    db.commit()
    db.refresh(prefs)
    return prefs


def _resolve_timezone(tz_name: str | None) -> tuple[ZoneInfo, str]:
    if not tz_name:
        return ZoneInfo("UTC"), "UTC"
    candidate = tz_name.strip()
    if not candidate:
        return ZoneInfo("UTC"), "UTC"
    try:
        return ZoneInfo(candidate), candidate
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC"), "UTC"


def _enqueue_transcription(session: CaptureSession, db: Session) -> None:
    try:
        celery_app.send_task("app.workers.tasks.process_session_transcription", args=[session.id], queue="transcription")
    except Exception as exc:  # noqa: BLE001
        session.status = SessionStatus.failed.value
        session.error_message = f"Failed to enqueue transcription: {exc}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Capture stored, but transcription queue is unavailable",
        ) from exc


def _get_or_create_ios_app_device(db: Session, user: AppUser) -> Device:
    device_code = f"ios-app-{user.id}"
    now = utc_now()

    device = db.scalar(select(Device).where(Device.device_code == device_code))
    if not device:
        device = Device(
            device_code=device_code,
            secret_hash=hash_secret(secrets.token_urlsafe(24)),
            is_active=True,
            firmware_version="ios-app",
            last_seen_at=now,
        )
        db.add(device)
        db.flush()

    binding = db.scalar(
        select(DeviceUserBinding).where(
            DeviceUserBinding.device_id == device.id,
            DeviceUserBinding.user_id == user.id,
        )
    )
    if not binding:
        db.add(
            DeviceUserBinding(
                device_id=device.id,
                user_id=user.id,
                alias="iPhone Mic",
                is_active=True,
            )
        )
    elif not binding.is_active:
        binding.is_active = True

    device.last_seen_at = now
    if not device.firmware_version:
        device.firmware_version = "ios-app"

    return device


def _map_ai_item(item: AIItem) -> AppAssistantItemResponse:
    return AppAssistantItemResponse(
        item_id=item.id,
        extraction_id=item.extraction_id,
        session_id=item.session_id,
        transcript_id=item.transcript_id,
        item_type=item.item_type,
        title=item.title,
        details=item.details,
        due_at=item.due_at,
        timezone=item.timezone,
        priority=item.priority,
        status=item.status,
        source_segment_start_seconds=item.source_segment_start_seconds,
        source_segment_end_seconds=item.source_segment_end_seconds,
        created_at=item.created_at,
        updated_at=item.updated_at,
        completed_at=item.completed_at,
    )


def _map_app_me(user: AppUser) -> AppMeResponse:
    return AppMeResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        has_avatar=bool(user.avatar_blob),
        avatar_updated_at=user.avatar_updated_at,
        created_at=user.created_at,
    )


def _map_ai_extraction(extraction: AIExtraction) -> AppCaptureAIExtractionResponse:
    return AppCaptureAIExtractionResponse(
        extraction_id=extraction.id,
        session_id=extraction.session_id,
        transcript_id=extraction.transcript_id,
        status=extraction.status,
        intent=extraction.intent,
        intent_confidence=extraction.intent_confidence,
        summary=extraction.summary,
        plan_steps=extraction.plan_json or [],
        model_name=extraction.model_name,
        error_message=extraction.error_message,
        created_at=extraction.created_at,
        started_at=extraction.started_at,
        completed_at=extraction.completed_at,
        updated_at=extraction.updated_at,
    )


def _map_founder_action(action: FounderIdeaAction) -> FounderIdeaActionResponse:
    return FounderIdeaActionResponse(
        action_id=action.id,
        idea_cluster_id=action.idea_cluster_id,
        title=action.title,
        details=action.details,
        status=action.status,
        priority=action.priority,
        due_at=action.due_at,
        source=action.source,
        created_at=action.created_at,
        updated_at=action.updated_at,
        completed_at=action.completed_at,
    )


def _map_founder_idea(idea: FounderIdeaCluster) -> FounderIdeaClusterResponse:
    return FounderIdeaClusterResponse(
        idea_id=idea.id,
        title=idea.title,
        summary=idea.summary,
        problem_statement=idea.problem_statement,
        proposed_solution=idea.proposed_solution,
        target_user=idea.target_user,
        status=idea.status,
        confidence=idea.confidence,
        novelty_score=idea.novelty_score,
        conviction_score=idea.conviction_score,
        mention_count=idea.mention_count,
        first_seen_at=idea.first_seen_at,
        last_seen_at=idea.last_seen_at,
        created_at=idea.created_at,
        updated_at=idea.updated_at,
    )


def _map_founder_signal(signal: FounderSignal) -> FounderSignalResponse:
    return FounderSignalResponse(
        signal_id=signal.id,
        signal_type=signal.signal_type,
        title=signal.title,
        summary=signal.summary,
        strength=signal.strength,
        session_id=signal.session_id,
        transcript_id=signal.transcript_id,
        idea_cluster_id=signal.idea_cluster_id,
        created_at=signal.created_at,
    )


def _map_memory_link(link: MemoryLink) -> MemoryLinkResponse:
    entity = None
    founder_idea = None
    if link.entity is not None:
        entity = MemoryLinkedEntityResponse(
            entity_id=link.entity.id,
            entity_type=link.entity.entity_type,
            name=link.entity.name,
        )
    if link.founder_idea is not None:
        founder_idea = MemoryLinkedFounderIdeaResponse(
            idea_id=link.founder_idea.id,
            title=link.founder_idea.title,
            status=link.founder_idea.status,
        )
    return MemoryLinkResponse(
        link_id=link.id,
        session_id=link.session_id,
        link_type=link.link_type,
        source=link.source,
        status=link.status,
        confidence=link.confidence,
        created_at=link.created_at,
        updated_at=link.updated_at,
        entity=entity,
        founder_idea=founder_idea,
    )


def _resolve_memory_card_fields(
    session: CaptureSession,
    *,
    transcript_text: str | None = None,
    assistant_summary: str | None = None,
) -> tuple[str | None, str | None]:
    if session.memory_title and session.memory_gist:
        return session.memory_title, session.memory_gist
    if transcript_text or assistant_summary:
        return build_memory_card_fallback(
            transcript_text,
            assistant_summary=assistant_summary,
        )
    return None, None


def _get_owned_capture_session(db: Session, *, user_id: str, session_id: str):
    session = db.scalar(
        select(CaptureSession)
        .join(
            DeviceUserBinding,
            (DeviceUserBinding.device_id == CaptureSession.device_id)
            & (DeviceUserBinding.user_id == user_id)
            & (DeviceUserBinding.is_active.is_(True)),
        )
        .where(CaptureSession.id == session_id)
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.post("/register", response_model=AppTokenResponse, status_code=status.HTTP_201_CREATED)
def register_app_user(payload: AppRegisterRequest, db: Session = Depends(get_db)) -> AppTokenResponse:
    email = payload.email.lower().strip()

    existing = db.scalar(select(AppUser).where(AppUser.email == email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user = AppUser(email=email, password_hash=hash_secret(payload.password), full_name=payload.full_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(AppUserPreferences(user_id=user.id))
    db.commit()

    settings = get_settings()
    token = create_app_access_token(user.id)
    return AppTokenResponse(access_token=token, expires_in_minutes=settings.jwt_expires_minutes)


@router.post("/auth", response_model=AppTokenResponse)
def auth_app_user(payload: AppAuthRequest, db: Session = Depends(get_db)) -> AppTokenResponse:
    email = payload.email.lower().strip()

    user = db.scalar(select(AppUser).where(AppUser.email == email))
    if not user or not user.is_active or not verify_secret(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    settings = get_settings()
    token = create_app_access_token(user.id)
    return AppTokenResponse(access_token=token, expires_in_minutes=settings.jwt_expires_minutes)


from app.services.email import send_reset_email

@router.post("/password/forgot/request", response_model=AppForgotPasswordRequestResponse)
def request_password_reset(payload: AppForgotPasswordRequest, db: Session = Depends(get_db)) -> AppForgotPasswordRequestResponse:
    email = payload.email.lower().strip()
    now = datetime.now(timezone.utc)
    settings = get_settings()
    generic_message = "If the account exists, a reset token has been issued."

    user = db.scalar(select(AppUser).where(AppUser.email == email, AppUser.is_active.is_(True)))
    if not user:
        return AppForgotPasswordRequestResponse(
            status="accepted",
            message=generic_message,
            expires_in_seconds=settings.password_reset_token_ttl_seconds,
        )

    db.execute(
        delete(AppPasswordResetToken).where(
            AppPasswordResetToken.user_id == user.id,
            AppPasswordResetToken.used_at.is_(None),
        )
    )

    reset_token = secrets.token_urlsafe(24)
    expires_at = now + timedelta(seconds=settings.password_reset_token_ttl_seconds)
    db.add(
        AppPasswordResetToken(
            user_id=user.id,
            token_hash=hash_pair_token(reset_token),
            expires_at=expires_at,
        )
    )
    db.commit()

    # Dispatch the beautiful HTML email to our local Mailpit instance!
    send_reset_email(to_email=user.email, reset_token=reset_token)

    expose_token = settings.environment.lower() != "production"
    return AppForgotPasswordRequestResponse(
        status="accepted",
        message=generic_message,
        expires_in_seconds=settings.password_reset_token_ttl_seconds,
        reset_token=reset_token if expose_token else None,
    )


@router.post("/password/forgot/confirm", response_model=AppActionStatusResponse)
def confirm_password_reset(payload: AppForgotPasswordConfirmRequest, db: Session = Depends(get_db)) -> AppActionStatusResponse:
    email = payload.email.lower().strip()
    now = datetime.now(timezone.utc)
    token_hash = hash_pair_token(payload.reset_token.strip())

    user = db.scalar(select(AppUser).where(AppUser.email == email, AppUser.is_active.is_(True)))
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

    reset_session = db.scalar(
        select(AppPasswordResetToken)
        .where(
            AppPasswordResetToken.user_id == user.id,
            AppPasswordResetToken.token_hash == token_hash,
            AppPasswordResetToken.used_at.is_(None),
            AppPasswordResetToken.expires_at > now,
        )
        .order_by(AppPasswordResetToken.requested_at.desc())
    )
    if not reset_session:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

    user.password_hash = hash_secret(payload.new_password)
    reset_session.used_at = now

    db.execute(
        delete(AppPasswordResetToken).where(
            AppPasswordResetToken.user_id == user.id,
            AppPasswordResetToken.id != reset_session.id,
        )
    )
    db.commit()

    return AppActionStatusResponse(status="password_reset", message="Password reset successful")


@router.get("/me", response_model=AppMeResponse)
def get_current_app_user_profile(
    user: AppUser = Depends(get_current_app_user),
) -> AppMeResponse:
    return _map_app_me(user)


@router.patch("/me", response_model=AppMeResponse)
def update_current_app_user_profile(
    payload: AppMeUpdateRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppMeResponse:
    if payload.full_name is not None:
        value = payload.full_name.strip()
        user.full_name = value or None
    db.commit()
    db.refresh(user)
    return _map_app_me(user)


@router.get("/me/avatar")
def get_current_app_user_avatar(
    user: AppUser = Depends(get_current_app_user),
) -> StreamingResponse:
    if not user.avatar_blob or not user.avatar_content_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile photo not found")

    headers = {
        "Content-Length": str(len(user.avatar_blob)),
        "Cache-Control": "private, max-age=300",
    }
    return StreamingResponse(
        io.BytesIO(user.avatar_blob),
        media_type=user.avatar_content_type,
        headers=headers,
    )


@router.put("/me/avatar", response_model=AppMeResponse)
async def upload_current_app_user_avatar(
    request: Request,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppMeResponse:
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    allowed_types = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Profile photo must be JPEG, PNG, HEIC, HEIF, or WEBP",
        )

    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profile photo payload is empty")
    max_bytes = 10 * 1024 * 1024
    if len(image_bytes) > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Profile photo exceeds 10 MB")

    user.avatar_blob = image_bytes
    user.avatar_content_type = content_type
    user.avatar_file_size_bytes = len(image_bytes)
    user.avatar_updated_at = utc_now()
    db.commit()
    db.refresh(user)
    return _map_app_me(user)


@router.delete("/me/avatar", response_model=AppMeResponse)
def delete_current_app_user_avatar(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppMeResponse:
    user.avatar_blob = None
    user.avatar_content_type = None
    user.avatar_file_size_bytes = None
    user.avatar_updated_at = None
    db.commit()
    db.refresh(user)
    return _map_app_me(user)


@router.get("/me/preferences", response_model=AppUserPreferencesResponse)
def get_current_app_user_preferences(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppUserPreferencesResponse:
    prefs = _get_or_create_preferences(db, user.id)
    if prefs.tts_provider != "elevenlabs":
        prefs.tts_provider = "elevenlabs"
        db.commit()
        db.refresh(prefs)
    return AppUserPreferencesResponse(
        timezone=prefs.timezone,
        daily_summary_enabled=prefs.daily_summary_enabled,
        reminder_notifications_enabled=prefs.reminder_notifications_enabled,
        calendar_export_default_enabled=prefs.calendar_export_default_enabled,
        tts_provider=prefs.tts_provider,
        updated_at=prefs.updated_at,
    )


@router.patch("/me/preferences", response_model=AppUserPreferencesResponse)
def update_current_app_user_preferences(
    payload: AppUserPreferencesUpdateRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppUserPreferencesResponse:
    prefs = _get_or_create_preferences(db, user.id)

    if payload.timezone is not None:
        _, normalized = _resolve_timezone(payload.timezone)
        prefs.timezone = normalized
    if payload.daily_summary_enabled is not None:
        prefs.daily_summary_enabled = payload.daily_summary_enabled
    if payload.reminder_notifications_enabled is not None:
        prefs.reminder_notifications_enabled = payload.reminder_notifications_enabled
    if payload.calendar_export_default_enabled is not None:
        prefs.calendar_export_default_enabled = payload.calendar_export_default_enabled
    if payload.tts_provider is not None:
        prefs.tts_provider = "elevenlabs"

    db.commit()
    db.refresh(prefs)
    return AppUserPreferencesResponse(
        timezone=prefs.timezone,
        daily_summary_enabled=prefs.daily_summary_enabled,
        reminder_notifications_enabled=prefs.reminder_notifications_enabled,
        calendar_export_default_enabled=prefs.calendar_export_default_enabled,
        tts_provider=prefs.tts_provider,
        updated_at=prefs.updated_at,
    )


@router.post("/me/delete", response_model=AppActionStatusResponse)
def delete_current_app_user(
    payload: AppDeleteAccountRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppActionStatusResponse:
    if not verify_secret(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user_id = user.id
    db.execute(delete(DeviceUserBinding).where(DeviceUserBinding.user_id == user_id))
    db.execute(delete(PairingSession).where(PairingSession.user_id == user_id))
    db.execute(delete(AppPasswordResetToken).where(AppPasswordResetToken.user_id == user_id))
    db.delete(user)
    db.commit()

    return AppActionStatusResponse(status="deleted", message="Account deleted")


@router.get("/devices", response_model=list[PairedDeviceResponse])
def list_user_devices(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> list[PairedDeviceResponse]:
    rows = db.execute(
        select(DeviceUserBinding, Device)
        .join(Device, Device.id == DeviceUserBinding.device_id)
        .where(DeviceUserBinding.user_id == user.id, DeviceUserBinding.is_active.is_(True))
        .order_by(DeviceUserBinding.paired_at.desc())
    ).all()

    device_ids = [device.id for _, device in rows]
    last_capture_by_device: dict[str, datetime] = {}
    if device_ids:
        capture_rows = db.execute(
            select(CaptureSession.device_id, func.max(CaptureSession.started_at))
            .where(CaptureSession.device_id.in_(device_ids))
            .group_by(CaptureSession.device_id)
        ).all()
        last_capture_by_device = {
            device_id: last_capture
            for device_id, last_capture in capture_rows
            if last_capture is not None
        }

    now = utc_now()
    return [
        PairedDeviceResponse(
            device_id=device.id,
            device_code=device.device_code,
            alias=binding.alias,
            paired_at=binding.paired_at,
            last_seen_at=device.last_seen_at,
            status=_device_status(device.last_seen_at, now),
            firmware_version=device.firmware_version,
            last_capture_at=last_capture_by_device.get(device.id),
        )
        for binding, device in rows
    ]


@router.patch("/devices/{device_id}", response_model=PairedDeviceResponse)
def update_user_device(
    device_id: str,
    payload: AppDeviceUpdateRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> PairedDeviceResponse:
    row = db.execute(
        select(DeviceUserBinding, Device)
        .join(Device, Device.id == DeviceUserBinding.device_id)
        .where(
            DeviceUserBinding.device_id == device_id,
            DeviceUserBinding.user_id == user.id,
            DeviceUserBinding.is_active.is_(True),
        )
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paired device not found")

    binding, device = row
    if payload.alias is not None:
        binding.alias = payload.alias.strip() if payload.alias.strip() else None
    db.commit()
    db.refresh(binding)
    db.refresh(device)

    last_capture_at = db.scalar(
        select(func.max(CaptureSession.started_at)).where(CaptureSession.device_id == device.id)
    )

    return PairedDeviceResponse(
        device_id=device.id,
        device_code=device.device_code,
        alias=binding.alias,
        paired_at=binding.paired_at,
        last_seen_at=device.last_seen_at,
        status=_device_status(device.last_seen_at, utc_now()),
        firmware_version=device.firmware_version,
        last_capture_at=last_capture_at,
    )


@router.delete("/devices/{device_id}", response_model=AppActionStatusResponse)
def unpair_user_device(
    device_id: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppActionStatusResponse:
    binding = db.scalar(
        select(DeviceUserBinding).where(
            DeviceUserBinding.device_id == device_id,
            DeviceUserBinding.user_id == user.id,
            DeviceUserBinding.is_active.is_(True),
        )
    )
    if not binding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paired device not found")

    binding.is_active = False
    db.commit()
    return AppActionStatusResponse(status="unpaired", message="Device unpaired")


@router.post("/live/start")
def start_live_stream_for_app() -> dict:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Live packet streaming is deprecated. Use device direct capture session APIs: /v1/device/capture/sessions, /v1/device/capture/chunks, /v1/device/capture/sessions/{id}/finalize.",
    )


@router.post("/devices/{device_id}/network-profile", response_model=AppQueueNetworkProfileResponse)
def queue_device_network_profile(
    device_id: str,
    payload: AppQueueNetworkProfileRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppQueueNetworkProfileResponse:
    binding = db.scalar(
        select(DeviceUserBinding).where(
            DeviceUserBinding.device_id == device_id,
            DeviceUserBinding.user_id == user.id,
            DeviceUserBinding.is_active.is_(True),
        )
    )
    if not binding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paired device not found")

    normalized_ssid = payload.ssid.strip()
    if not normalized_ssid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSID cannot be empty")

    queue_network_profile(
        device_id=device_id,
        ssid=normalized_ssid,
        password=payload.password,
        source=payload.source.strip() or "app_manual",
    )
    return AppQueueNetworkProfileResponse(status="queued", expires_in_seconds=NETWORK_PROFILE_TTL_SECONDS)


@router.get("/dashboard/daily-summary", response_model=AppDailySummaryResponse)
def get_dashboard_daily_summary(
    summary_date: str | None = Query(default=None, alias="date"),
    tz: str | None = None,
    device_id: str | None = None,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppDailySummaryResponse:
    prefs = _get_or_create_preferences(db, user.id)
    tzinfo, tz_name = _resolve_timezone(tz or prefs.timezone)

    if summary_date:
        try:
            selected_date = date.fromisoformat(summary_date)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="date must be YYYY-MM-DD") from exc
    else:
        selected_date = utc_now().astimezone(tzinfo).date()

    day_start_local = datetime.combine(selected_date, time.min, tzinfo=tzinfo)
    day_end_local = datetime.combine(selected_date, time.max, tzinfo=tzinfo)
    day_start_utc = day_start_local.astimezone(timezone.utc)
    day_end_utc = day_end_local.astimezone(timezone.utc)
    now_utc = utc_now()
    next_24h_utc = now_utc + timedelta(hours=24)

    device_rows = db.execute(
        select(DeviceUserBinding, Device)
        .join(Device, Device.id == DeviceUserBinding.device_id)
        .where(DeviceUserBinding.user_id == user.id, DeviceUserBinding.is_active.is_(True))
    ).all()
    if not device_rows:
        return AppDailySummaryResponse(
            date=selected_date.isoformat(),
            timezone=tz_name,
            headline="No paired devices yet. Pair a device to start collecting memories.",
            generated_at=utc_now(),
            metrics=AppDailySummaryMetrics(
                memories_count=0,
                transcript_ready_count=0,
                open_actions_due_count=0,
                upcoming_events_count=0,
                top_intent=None,
                device_count=0,
            ),
            focus_items=[],
            device_breakdown=[],
        )

    active_device_ids = {device.id for _, device in device_rows}
    if device_id:
        if device_id not in active_device_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paired device not found")
        scoped_device_ids = {device_id}
    else:
        scoped_device_ids = active_device_ids

    device_code_by_id = {device.id: device.device_code for _, device in device_rows}

    session_rows = db.execute(
        select(CaptureSession.id, CaptureSession.device_id)
        .where(
            CaptureSession.device_id.in_(scoped_device_ids),
            CaptureSession.started_at >= day_start_utc,
            CaptureSession.started_at <= day_end_utc,
        )
    ).all()
    session_ids = [session_id for session_id, _ in session_rows]
    session_device_map = {session_id: device_id_value for session_id, device_id_value in session_rows}

    transcript_ready_ids: set[str] = set()
    if session_ids:
        transcript_rows = db.execute(
            select(Transcript.session_id).where(Transcript.session_id.in_(session_ids))
        ).all()
        transcript_ready_ids = {row[0] for row in transcript_rows}

    top_intent: str | None = None
    if session_ids:
        top_intent_row = db.execute(
            select(AIExtraction.intent, func.count(AIExtraction.id).label("intent_count"))
            .where(
                AIExtraction.user_id == user.id,
                AIExtraction.session_id.in_(session_ids),
                AIExtraction.intent.is_not(None),
                AIExtraction.intent != "",
            )
            .group_by(AIExtraction.intent)
            .order_by(func.count(AIExtraction.id).desc())
            .limit(1)
        ).first()
        if top_intent_row:
            top_intent = top_intent_row[0]

    open_items_rows = db.execute(
        select(AIItem, CaptureSession.device_id)
        .join(CaptureSession, CaptureSession.id == AIItem.session_id)
        .where(
            AIItem.user_id == user.id,
            CaptureSession.device_id.in_(scoped_device_ids),
            AIItem.status.in_(["open", "snoozed"]),
        )
    ).all()

    open_actions_due_count = 0
    open_reminders_due_count = 0
    upcoming_events_count = 0

    by_device_memories: dict[str, int] = {did: 0 for did in scoped_device_ids}
    by_device_transcripts: dict[str, int] = {did: 0 for did in scoped_device_ids}
    by_device_open_actions: dict[str, int] = {did: 0 for did in scoped_device_ids}
    by_device_upcoming: dict[str, int] = {did: 0 for did in scoped_device_ids}

    for _, device_id_value in session_rows:
        by_device_memories[device_id_value] = by_device_memories.get(device_id_value, 0) + 1
    for session_id in transcript_ready_ids:
        mapped_device = session_device_map.get(session_id)
        if mapped_device:
            by_device_transcripts[mapped_device] = by_device_transcripts.get(mapped_device, 0) + 1

    focus_candidates: list[tuple[datetime, AIItem, str]] = []
    for item, item_device_id in open_items_rows:
        due = item.due_at
        if due is not None and due <= day_end_utc:
            if item.item_type == "reminder":
                open_reminders_due_count += 1
            else:
                open_actions_due_count += 1
                by_device_open_actions[item_device_id] = by_device_open_actions.get(item_device_id, 0) + 1

        if due is not None and due >= now_utc and due <= next_24h_utc:
            upcoming_events_count += 1
            by_device_upcoming[item_device_id] = by_device_upcoming.get(item_device_id, 0) + 1

        sort_due = due or datetime.max.replace(tzinfo=timezone.utc)
        focus_candidates.append((sort_due, item, item_device_id))

    focus_candidates.sort(key=lambda entry: (entry[0], entry[1].created_at))
    focus_items = [
        AppDailySummaryFocusItem(
            item_id=item.id,
            item_type=item.item_type,
            title=item.title,
            due_at=item.due_at,
            status=item.status,
            session_id=item.session_id,
            device_code=device_code_by_id.get(item_device_id),
        )
        for _, item, item_device_id in focus_candidates[:3]
    ]

    memories_count = len(session_ids)
    transcript_ready_count = len(transcript_ready_ids)
    device_count = len(scoped_device_ids)

    if memories_count == 0:
        headline = "No memories for this day yet. Start recording from your paired device."
    else:
        intent_phrase = f" Top intent: {top_intent}." if top_intent else ""
        headline = (
            f"Today you captured {memories_count} memories across {device_count} device"
            f"{'' if device_count == 1 else 's'}.{intent_phrase} "
            f"You have {open_actions_due_count + open_reminders_due_count} due actions/reminders and "
            f"{upcoming_events_count} upcoming events."
        )

    breakdown = [
        AppDailySummaryDeviceBreakdown(
            device_id=did,
            device_code=device_code_by_id.get(did, did),
            memories_count=by_device_memories.get(did, 0),
            transcript_ready_count=by_device_transcripts.get(did, 0),
            open_action_count=by_device_open_actions.get(did, 0),
            upcoming_event_count=by_device_upcoming.get(did, 0),
        )
        for did in sorted(scoped_device_ids, key=lambda value: device_code_by_id.get(value, value))
    ]

    return AppDailySummaryResponse(
        date=selected_date.isoformat(),
        timezone=tz_name,
        headline=headline,
        generated_at=utc_now(),
        metrics=AppDailySummaryMetrics(
            memories_count=memories_count,
            transcript_ready_count=transcript_ready_count,
            open_actions_due_count=open_actions_due_count + open_reminders_due_count,
            upcoming_events_count=upcoming_events_count,
            top_intent=top_intent,
            device_count=device_count,
        ),
        focus_items=focus_items,
        device_breakdown=breakdown,
    )


@router.post("/captures/upload-wav", response_model=AppCaptureUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_app_capture_wav(
    wav_bytes: bytes = Body(..., media_type="audio/wav"),
    x_sample_rate: int = Header(default=16000),
    x_channels: int = Header(default=1),
    x_codec: str = Header(default="pcm16le"),
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppCaptureUploadResponse:
    settings = get_settings()

    if len(wav_bytes) < 44:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="WAV payload is too small")
    if len(wav_bytes) > settings.max_db_audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"WAV payload exceeds {settings.max_db_audio_bytes} bytes",
        )
    if x_sample_rate < 8000 or x_sample_rate > 48000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Sample-Rate must be between 8000 and 48000")
    if x_channels < 1 or x_channels > 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Channels must be 1 or 2")

    codec = x_codec.strip().lower() or "pcm16le"
    device = _get_or_create_ios_app_device(db, user)

    session = CaptureSession(
        device_id=device.id,
        status=SessionStatus.queued.value,
        sample_rate=x_sample_rate,
        channels=x_channels,
        codec=codec,
        total_chunks=1,
        audio_blob_wav=wav_bytes,
        audio_blob_content_type="audio/wav",
        audio_blob_size_bytes=len(wav_bytes),
        finalized_at=utc_now(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    _enqueue_transcription(session, db)

    return AppCaptureUploadResponse(
        session_id=session.id,
        status=session.status,
        queued_for_transcription=True,
        audio_size_bytes=len(wav_bytes),
        sample_rate=session.sample_rate,
        channels=session.channels,
        codec=session.codec,
    )


@router.get("/captures", response_model=list[AppCaptureListItemResponse])
def list_user_captures(
    limit: int = 20,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> list[AppCaptureListItemResponse]:
    capped_limit = max(1, min(limit, 100))

    rows = db.execute(
        select(CaptureSession, Device, Transcript, AIExtraction)
        .join(Device, Device.id == CaptureSession.device_id)
        .join(
            DeviceUserBinding,
            (DeviceUserBinding.device_id == CaptureSession.device_id)
            & (DeviceUserBinding.user_id == user.id)
            & (DeviceUserBinding.is_active.is_(True)),
        )
        .outerjoin(Transcript, Transcript.session_id == CaptureSession.id)
        .outerjoin(AIExtraction, AIExtraction.session_id == CaptureSession.id)
        .order_by(CaptureSession.started_at.desc())
        .limit(capped_limit)
    ).all()

    items: list[AppCaptureListItemResponse] = []
    for session, device, transcript, extraction in rows:
        memory_title, memory_gist = _resolve_memory_card_fields(
            session,
            transcript_text=transcript.full_text if transcript else None,
            assistant_summary=extraction.summary if extraction else None,
        )
        items.append(
            AppCaptureListItemResponse(
                session_id=session.id,
                device_id=device.id,
                device_code=device.device_code,
                status=session.status,
                memory_title=memory_title,
                memory_gist=memory_gist,
                total_chunks=session.total_chunks,
                started_at=session.started_at,
                finalized_at=session.finalized_at,
                duration_seconds=transcript.duration_seconds if transcript else None,
                has_audio=bool((session.audio_blob_size_bytes or 0) > 0 or session.assembled_object_key),
            )
        )
    return items


@router.get("/memories/search", response_model=MemorySearchResponse)
def search_user_memories(
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
    entity_type: str | None = None,
    idea_id: str | None = None,
    has_tasks: bool | None = None,
    has_reminders: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> MemorySearchResponse:
    capped_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    normalized_entity_type = entity_type.strip().lower() if entity_type else None
    if normalized_entity_type and normalized_entity_type not in {"person", "project", "place"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid entity_type")

    result = search_memories(
        db,
        user_id=user.id,
        query=q,
        limit=capped_limit,
        offset=safe_offset,
        entity_type=normalized_entity_type,
        idea_id=idea_id,
        has_tasks=has_tasks,
        has_reminders=has_reminders,
        date_from=date_from,
        date_to=date_to,
    )
    return MemorySearchResponse(
        query=q,
        total=result["total"],
        limit=capped_limit,
        offset=safe_offset,
        results=[MemorySearchResultResponse(**row) for row in result["results"]],
    )


@router.post("/memories/ask", response_model=AppMemoryQueryResponse)
def ask_memories_semantically(
    payload: AppMemoryQueryRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppMemoryQueryResponse:
    """
    Perform a natural language query over all recorded memories using vector search and LLM synthesis.
    """
    result = query_memories_semantically(
        db=db,
        user_id=user.id,
        query=payload.query
    )
    return AppMemoryQueryResponse(**result)


def _encoded_header_text(value: str) -> str:
    return quote(value.strip(), safe="")


def _cleanup_voice_query(file_handle, temp_dir: str) -> None:
    try:
        file_handle.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/memories/ask-voice")
async def ask_memory_voice(
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
):
    temp_root = "/tmp/secondmind_voice"
    os.makedirs(temp_root, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix="ask_voice_", dir=temp_root)
    input_path = os.path.join(temp_dir, "query.wav")
    output_path = os.path.join(temp_dir, "answer.wav")

    try:
        with open(input_path, "wb") as input_file:
            while True:
                chunk = await audio.read(1024 * 1024)
                if not chunk:
                    break
                input_file.write(chunk)

        transcription = await asyncio.to_thread(lambda: get_transcriber().transcribe(input_path))
        query_text = str(transcription.get("full_text") or "").strip()
        if not query_text:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return JSONResponse(status_code=400, content={"error": "Could not understand audio"})

        try:
            memory_result = query_memories_semantically(db=db, user_id=user.id, query=query_text)
        except EmbeddingServiceError:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "error": "AI memory service is unavailable. Start LM Studio and check LMSTUDIO_BASE_URL.",
                    "query_text": query_text,
                },
            )
        raw_answer = str(memory_result.get("answer") or "").strip()
        spoken_answer = await asyncio.to_thread(refine_spoken_answer, query_text, raw_answer)
        prefs = _get_or_create_preferences(db, user.id)
        tts_provider = "elevenlabs"

        try:
            actual_tts_provider = await asyncio.to_thread(
                lambda: get_tts_service().synthesize_to_file(
                    spoken_answer,
                    output_path,
                    provider=tts_provider,
                )
            )
        except TTSServiceError:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return JSONResponse(
                status_code=200,
                content={
                    "answer": spoken_answer,
                    "query_text": query_text,
                    "sources": memory_result.get("sources") or [],
                    "tts_provider": tts_provider,
                    "tts_failed": True,
                },
            )

        output_file = open(output_path, "rb")
        return StreamingResponse(
            output_file,
            media_type="audio/wav",
            headers={
                "X-Query-Text": _encoded_header_text(query_text),
                "X-Answer-Text": _encoded_header_text(spoken_answer),
                "X-TTS-Provider": actual_tts_provider,
                "X-Text-Encoding": "uri",
            },
            background=BackgroundTask(_cleanup_voice_query, output_file, temp_dir),
        )
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


@router.get("/captures/{session_id}/links", response_model=list[MemoryLinkResponse])
def list_capture_links(
    session_id: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> list[MemoryLinkResponse]:
    _get_owned_capture_session(db, user_id=user.id, session_id=session_id)
    links = db.scalars(
        select(MemoryLink)
        .where(MemoryLink.user_id == user.id, MemoryLink.session_id == session_id)
        .options(selectinload(MemoryLink.entity), selectinload(MemoryLink.founder_idea))
        .order_by(
            MemoryLink.status.asc(),
            MemoryLink.created_at.asc(),
        )
    ).all()
    return [_map_memory_link(link) for link in links]


@router.post("/captures/{session_id}/links", response_model=MemoryLinkResponse, status_code=status.HTTP_201_CREATED)
def create_capture_link(
    session_id: str,
    payload: MemoryLinkCreateRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> MemoryLinkResponse:
    _get_owned_capture_session(db, user_id=user.id, session_id=session_id)

    link_type = payload.link_type.strip().lower()
    is_founder_link = link_type == MemoryLinkType.founder_idea.value
    has_existing_target = bool(payload.entity_id or payload.founder_idea_id)
    has_create_target = bool(payload.create_name and payload.create_name.strip())

    if has_existing_target and has_create_target:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose an existing target or create a new one, not both")
    if not has_existing_target and not has_create_target:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target is required")

    entity_id: str | None = None
    founder_idea_id: str | None = None
    source = MemoryLinkSource.manual.value

    if has_create_target:
        source = MemoryLinkSource.manual_created.value
        create_name = payload.create_name.strip()
        if is_founder_link:
            idea = create_founder_idea_for_link(
                db,
                user_id=user.id,
                title=create_name,
                summary=payload.create_summary,
                target_user=payload.create_target_user,
            )
            founder_idea_id = idea.id
        else:
            entity = create_or_reuse_entity_for_link(
                db,
                user_id=user.id,
                link_type=link_type,
                name=create_name,
            )
            entity_id = entity.id
    elif is_founder_link:
        if not payload.founder_idea_id or payload.entity_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="founder_idea links require founder_idea_id")
        idea = db.scalar(
            select(FounderIdeaCluster).where(
                FounderIdeaCluster.id == payload.founder_idea_id,
                FounderIdeaCluster.user_id == user.id,
            )
        )
        if not idea:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Founder idea not found")
        founder_idea_id = idea.id
    else:
        if not payload.entity_id or payload.founder_idea_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Entity links require entity_id")
        entity = db.scalar(
            select(Entity).where(
                Entity.id == payload.entity_id,
                Entity.user_id == user.id,
            )
        )
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
        if entity.entity_type != link_type:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Entity type does not match link_type")
        entity_id = entity.id

    link = upsert_memory_link(
        db,
        user_id=user.id,
        session_id=session_id,
        link_type=link_type,
        entity_id=entity_id,
        founder_idea_id=founder_idea_id,
        source=source,
        status=MemoryLinkStatus.confirmed.value,
        confidence=1.0 if source == MemoryLinkSource.manual_created.value else None,
    )
    db.commit()
    link = db.scalar(
        select(MemoryLink)
        .where(MemoryLink.id == link.id)
        .options(selectinload(MemoryLink.entity), selectinload(MemoryLink.founder_idea))
    )
    return _map_memory_link(link)


@router.patch("/captures/{session_id}/links/{link_id}", response_model=MemoryLinkResponse)
def update_capture_link(
    session_id: str,
    link_id: str,
    payload: MemoryLinkUpdateRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> MemoryLinkResponse:
    _get_owned_capture_session(db, user_id=user.id, session_id=session_id)
    link = db.scalar(
        select(MemoryLink)
        .where(
            MemoryLink.id == link_id,
            MemoryLink.user_id == user.id,
            MemoryLink.session_id == session_id,
        )
        .options(selectinload(MemoryLink.entity), selectinload(MemoryLink.founder_idea))
    )
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory link not found")

    if payload.status is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="status is required")
    link.status = payload.status
    db.commit()
    db.refresh(link)
    return _map_memory_link(link)


@router.delete("/captures/{session_id}/links/{link_id}", response_model=AppActionStatusResponse)
def delete_capture_link(
    session_id: str,
    link_id: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppActionStatusResponse:
    _get_owned_capture_session(db, user_id=user.id, session_id=session_id)
    link = db.scalar(
        select(MemoryLink).where(
            MemoryLink.id == link_id,
            MemoryLink.user_id == user.id,
            MemoryLink.session_id == session_id,
        )
    )
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory link not found")
    db.delete(link)
    db.commit()
    return AppActionStatusResponse(status="deleted", message="Memory link deleted")


@router.get("/link-targets/search", response_model=LinkTargetSearchResponse)
def search_link_targets(
    q: str = "",
    types: str | None = None,
    limit: int = 12,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> LinkTargetSearchResponse:
    capped_limit = max(1, min(limit, 50))
    requested_types = {
        part.strip().lower()
        for part in (types.split(",") if types else ["person", "project", "place", "founder_idea"])
        if part.strip()
    }
    allowed_types = {"person", "project", "place", "founder_idea"}
    invalid = requested_types - allowed_types
    if invalid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid types: {', '.join(sorted(invalid))}")

    query_text = q.strip().lower()
    like_query = f"%{query_text.replace('%', '').replace('_', '').strip()}%" if query_text else None

    entities: list[LinkTargetSearchEntityResponse] = []
    founder_ideas: list[LinkTargetSearchFounderIdeaResponse] = []

    entity_types = sorted(requested_types & {"person", "project", "place"})
    if entity_types:
        stmt = select(Entity).where(Entity.user_id == user.id, Entity.entity_type.in_(entity_types))
        if like_query:
            stmt = stmt.where(
                or_(
                    func.lower(Entity.name).like(like_query, escape="\\"),
                    Entity.normalized_name.like(like_query, escape="\\"),
                )
            )
        entity_rows = db.scalars(
            stmt.order_by(Entity.mention_count.desc(), Entity.last_seen_at.desc()).limit(capped_limit)
        ).all()
        entities = [
            LinkTargetSearchEntityResponse(
                entity_id=row.id,
                entity_type=row.entity_type,
                name=row.name,
                mention_count=row.mention_count,
            )
            for row in entity_rows
        ]

    if "founder_idea" in requested_types:
        stmt = select(FounderIdeaCluster).where(FounderIdeaCluster.user_id == user.id)
        if like_query:
            stmt = stmt.where(
                or_(
                    func.lower(FounderIdeaCluster.title).like(like_query, escape="\\"),
                    func.lower(func.coalesce(FounderIdeaCluster.summary, "")).like(like_query, escape="\\"),
                    func.lower(func.coalesce(FounderIdeaCluster.target_user, "")).like(like_query, escape="\\"),
                )
            )
        idea_rows = db.scalars(
            stmt.order_by(FounderIdeaCluster.last_seen_at.desc(), FounderIdeaCluster.mention_count.desc()).limit(capped_limit)
        ).all()
        founder_ideas = [
            LinkTargetSearchFounderIdeaResponse(
                idea_id=row.id,
                title=row.title,
                status=row.status,
                mention_count=row.mention_count,
            )
            for row in idea_rows
        ]

    return LinkTargetSearchResponse(entities=entities, founder_ideas=founder_ideas)


@router.get("/captures/{session_id}/transcript", response_model=AppCaptureTranscriptResponse)
def get_user_capture_transcript(
    session_id: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppCaptureTranscriptResponse:
    session = db.scalar(
        select(CaptureSession)
        .join(
            DeviceUserBinding,
            (DeviceUserBinding.device_id == CaptureSession.device_id)
            & (DeviceUserBinding.user_id == user.id)
            & (DeviceUserBinding.is_active.is_(True)),
        )
        .where(CaptureSession.id == session_id)
        .options(selectinload(CaptureSession.transcript))
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    transcript = session.transcript
    if not transcript:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not ready")

    return AppCaptureTranscriptResponse(
        session_id=session.id,
        model_name=transcript.model_name,
        language=transcript.language,
        full_text=transcript.full_text,
        duration_seconds=transcript.duration_seconds,
    )


@router.get("/captures/{session_id}/audio")
def stream_user_capture_audio(
    session_id: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> Response:
    session = db.scalar(
        select(CaptureSession)
        .join(
            DeviceUserBinding,
            (DeviceUserBinding.device_id == CaptureSession.device_id)
            & (DeviceUserBinding.user_id == user.id)
            & (DeviceUserBinding.is_active.is_(True)),
        )
        .where(CaptureSession.id == session_id)
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.audio_blob_wav:
        headers = {
            "Content-Disposition": f'inline; filename="{session.id}.wav"',
            "Cache-Control": "no-store",
        }
        return StreamingResponse(io.BytesIO(session.audio_blob_wav), media_type="audio/wav", headers=headers)

    if not session.assembled_object_key:
        if session.status in {SessionStatus.receiving.value, SessionStatus.queued.value, SessionStatus.transcribing.value}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Audio not ready yet")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assembled audio not found")

    audio_bytes = get_storage().get_bytes(session.assembled_object_key)
    headers = {
        "Content-Disposition": f'inline; filename="{session.id}.wav"',
        "Cache-Control": "no-store",
    }
    return Response(content=audio_bytes, media_type="audio/wav", headers=headers)


@router.get("/captures/{session_id}/ai", response_model=AppCaptureAIResponse)
def get_user_capture_ai(
    session_id: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppCaptureAIResponse:
    session = db.scalar(
        select(CaptureSession)
        .join(
            DeviceUserBinding,
            (DeviceUserBinding.device_id == CaptureSession.device_id)
            & (DeviceUserBinding.user_id == user.id)
            & (DeviceUserBinding.is_active.is_(True)),
        )
        .where(CaptureSession.id == session_id)
        .options(selectinload(CaptureSession.transcript))
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    transcript = session.transcript
    if not transcript:
        return AppCaptureAIResponse(
            session_id=session.id,
            transcript_ready=False,
            extraction=None,
            items=[],
        )

    extraction = db.scalar(select(AIExtraction).where(AIExtraction.transcript_id == transcript.id))
    if not extraction:
        return AppCaptureAIResponse(
            session_id=session.id,
            transcript_ready=True,
            extraction=None,
            items=[],
        )

    items = db.scalars(
        select(AIItem).where(AIItem.extraction_id == extraction.id).order_by(AIItem.created_at.asc())
    ).all()
    return AppCaptureAIResponse(
        session_id=session.id,
        transcript_ready=True,
        extraction=_map_ai_extraction(extraction),
        items=[_map_ai_item(item) for item in items],
    )


@router.get("/assistant/items", response_model=list[AppAssistantItemResponse])
def list_user_assistant_items(
    item_type: str | None = None,
    item_status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> list[AppAssistantItemResponse]:
    capped_limit = max(1, min(limit, 200))

    allowed_types = {"task", "reminder", "plan_step"}
    allowed_status = {"open", "done", "dismissed", "snoozed"}

    normalized_type = item_type.strip().lower() if item_type else None
    normalized_status = item_status.strip().lower() if item_status else None

    if normalized_type and normalized_type not in allowed_types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item_type")
    if normalized_status and normalized_status not in allowed_status:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item_status")

    query = select(AIItem).where(AIItem.user_id == user.id)
    if normalized_type:
        query = query.where(AIItem.item_type == normalized_type)
    if normalized_status:
        query = query.where(AIItem.status == normalized_status)

    rows = db.scalars(
        query.order_by(
            AIItem.due_at.is_(None),
            AIItem.due_at.asc(),
            AIItem.created_at.desc(),
        ).limit(capped_limit)
    ).all()
    return [_map_ai_item(item) for item in rows]


@router.patch("/assistant/items/{item_id}", response_model=AppAssistantItemResponse)
def update_assistant_item(
    item_id: str,
    payload: AppAssistantItemUpdateRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppAssistantItemResponse:
    item = db.scalar(select(AIItem).where(AIItem.id == item_id, AIItem.user_id == user.id))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assistant item not found")

    now = utc_now()
    if payload.snooze_minutes is not None:
        item.due_at = now + timedelta(minutes=payload.snooze_minutes)
        item.timezone = payload.timezone or item.timezone or "UTC"
        item.status = AIItemStatus.snoozed.value
        item.completed_at = None

    if payload.due_at is not None:
        item.due_at = payload.due_at
    if payload.timezone is not None:
        item.timezone = payload.timezone.strip() or None

    if payload.status is not None:
        new_status = payload.status.strip().lower()
        if new_status not in [s.value for s in AIItemStatus]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {new_status}. Must be one of: {[s.value for s in AIItemStatus]}"
            )
        
        item.status = new_status
        if item.status == AIItemStatus.done.value:
            item.completed_at = now
        else:
            item.completed_at = None

    db.commit()
    db.refresh(item)
    return _map_ai_item(item)


@router.post("/captures/{session_id}/ai/reprocess", response_model=AppCaptureAIReprocessResponse)
def reprocess_capture_ai(
    session_id: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> AppCaptureAIReprocessResponse:
    session = db.scalar(
        select(CaptureSession)
        .join(
            DeviceUserBinding,
            (DeviceUserBinding.device_id == CaptureSession.device_id)
            & (DeviceUserBinding.user_id == user.id)
            & (DeviceUserBinding.is_active.is_(True)),
        )
        .where(CaptureSession.id == session_id)
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    try:
        _, _, extraction = prepare_extraction_record(db, session_id, force_reset=True)
        db.commit()
    except AssistantPipelineError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    try:
        # Commit 'queued' status BEFORE sending to celery to avoid race condition
        extraction.status = "queued"
        extraction.error_message = None
        db.commit()
        
        celery_app.send_task("app.workers.tasks.process_session_ai_extraction", args=[session_id], queue="ai")
        queued = True
    except Exception as exc:  # noqa: BLE001
        extraction.status = "failed"
        extraction.error_message = f"Failed to enqueue AI extraction: {exc}"
        db.commit()
        queued = False

    db.refresh(extraction)
    return AppCaptureAIReprocessResponse(
        session_id=session_id,
        extraction_id=extraction.id,
        status=extraction.status,
        queued=queued,
    )


# ─────────────────────────────────────────────────────
# FOUNDER INTELLIGENCE ENDPOINTS
# ─────────────────────────────────────────────────────


@router.get("/founder/ideas", response_model=FounderIdeasListResponse)
def list_founder_ideas(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 50,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> FounderIdeasListResponse:
    capped_limit = max(1, min(limit, 200))
    query = select(FounderIdeaCluster).where(FounderIdeaCluster.user_id == user.id)
    if status_filter:
        normalized = status_filter.strip().lower()
        allowed = {"emerging", "active", "validating", "paused", "dropped"}
        if normalized not in allowed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid founder idea status")
        query = query.where(FounderIdeaCluster.status == normalized)

    ideas = db.scalars(
        query.order_by(
            FounderIdeaCluster.last_seen_at.desc(),
            FounderIdeaCluster.conviction_score.desc().nullslast(),
            FounderIdeaCluster.created_at.desc(),
        ).limit(capped_limit)
    ).all()
    return FounderIdeasListResponse(ideas=[_map_founder_idea(idea) for idea in ideas], total=len(ideas))


@router.get("/founder/ideas/{idea_id}", response_model=FounderIdeaDetailResponse)
def get_founder_idea_detail(
    idea_id: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> FounderIdeaDetailResponse:
    idea = db.scalar(
        select(FounderIdeaCluster).where(FounderIdeaCluster.id == idea_id, FounderIdeaCluster.user_id == user.id)
    )
    if not idea:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Founder idea not found")

    memories = db.scalars(
        select(FounderIdeaMemory)
        .where(FounderIdeaMemory.idea_cluster_id == idea.id)
        .order_by(FounderIdeaMemory.created_at.desc())
        .limit(24)
    ).all()
    actions = db.scalars(
        select(FounderIdeaAction)
        .where(FounderIdeaAction.idea_cluster_id == idea.id)
        .order_by(
            FounderIdeaAction.status.asc(),
            FounderIdeaAction.due_at.asc().nullslast(),
            FounderIdeaAction.created_at.desc(),
        )
        .limit(24)
    ).all()
    linked_signal_count = int(
        db.scalar(select(func.count(FounderSignal.id)).where(FounderSignal.idea_cluster_id == idea.id)) or 0
    )
    return FounderIdeaDetailResponse(
        **_map_founder_idea(idea).model_dump(),
        memories=[
            {
                "memory_id": row.id,
                "session_id": row.session_id,
                "transcript_id": row.transcript_id,
                "relevance_score": row.relevance_score,
                "role": row.role,
                "created_at": row.created_at,
            }
            for row in memories
        ],
        actions=[_map_founder_action(action) for action in actions],
        linked_signal_count=linked_signal_count,
    )


@router.get("/founder/signals", response_model=FounderSignalsListResponse)
def list_founder_signals(
    signal_type: str | None = None,
    limit: int = 60,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> FounderSignalsListResponse:
    capped_limit = max(1, min(limit, 200))
    query = select(FounderSignal).where(FounderSignal.user_id == user.id)
    if signal_type:
        normalized = signal_type.strip().lower()
        allowed = {"pain_point", "obsession", "contradiction", "opportunity", "market_signal"}
        if normalized not in allowed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid founder signal type")
        query = query.where(FounderSignal.signal_type == normalized)

    signals = db.scalars(
        query.order_by(
            FounderSignal.created_at.desc(),
            FounderSignal.strength.desc().nullslast(),
        ).limit(capped_limit)
    ).all()
    return FounderSignalsListResponse(signals=[_map_founder_signal(row) for row in signals], total=len(signals))


@router.get("/founder/weekly-memo", response_model=FounderWeeklyMemoResponse)
def get_founder_weekly_memo(
    week_start: str | None = None,
    tz: str | None = None,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> FounderWeeklyMemoResponse:
    prefs = _get_or_create_preferences(db, user.id)
    tzinfo, _ = _resolve_timezone(tz or prefs.timezone)
    if week_start:
        try:
            target_week = date.fromisoformat(week_start)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="week_start must be YYYY-MM-DD") from exc
    else:
        today_local = utc_now().astimezone(tzinfo)
        target_week = today_local.date() - timedelta(days=today_local.weekday())

    memo = db.scalar(
        select(WeeklyFounderMemo).where(
            WeeklyFounderMemo.user_id == user.id,
            WeeklyFounderMemo.week_start == target_week,
        )
    )
    if memo:
        return FounderWeeklyMemoResponse(
            memo_id=memo.id,
            week_start=memo.week_start,
            headline=memo.headline or "Founder weekly memo",
            memo_text=memo.memo_text or "No memo text generated yet.",
            top_ideas=memo.top_ideas_json or [],
            top_risks=memo.top_risks_json or [],
            top_actions=memo.top_actions_json or [],
            created_at=memo.created_at,
            updated_at=memo.updated_at,
        )

    top_ideas = db.scalars(
        select(FounderIdeaCluster)
        .where(FounderIdeaCluster.user_id == user.id)
        .order_by(FounderIdeaCluster.last_seen_at.desc(), FounderIdeaCluster.conviction_score.desc().nullslast())
        .limit(3)
    ).all()
    top_signals = db.scalars(
        select(FounderSignal)
        .where(FounderSignal.user_id == user.id)
        .order_by(FounderSignal.created_at.desc(), FounderSignal.strength.desc().nullslast())
        .limit(5)
    ).all()
    return FounderWeeklyMemoResponse(
        memo_id=None,
        week_start=target_week,
        headline="Founder weekly memo",
        memo_text="Founder intelligence is collecting enough signal to generate a weekly memo. Keep capturing product thoughts and startup discussions.",
        top_ideas=[
            {
                "idea_id": idea.id,
                "title": idea.title,
                "status": idea.status,
                "confidence": idea.confidence,
            }
            for idea in top_ideas
        ],
        top_risks=[signal.title for signal in top_signals if signal.signal_type == "contradiction"][:5],
        top_actions=[],
    )


@router.patch("/founder/actions/{action_id}", response_model=FounderIdeaActionResponse)
def update_founder_action(
    action_id: str,
    payload: FounderIdeaActionUpdateRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> FounderIdeaActionResponse:
    action = db.scalar(
        select(FounderIdeaAction).where(
            FounderIdeaAction.id == action_id,
            FounderIdeaAction.user_id == user.id,
        )
    )
    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Founder action not found")

    if payload.priority is not None:
        action.priority = payload.priority
    if payload.due_at is not None:
        action.due_at = payload.due_at
    if payload.status is not None:
        action.status = payload.status
        action.completed_at = utc_now() if payload.status == FounderIdeaActionStatus.done.value else None

    db.commit()
    db.refresh(action)
    return _map_founder_action(action)


# ─────────────────────────────────────────────────────
# IDEA GRAPH ENDPOINTS
# ─────────────────────────────────────────────────────

@router.get("/idea-graph", response_model=IdeaGraphResponse)
def get_idea_graph(
    entity_type: str | None = None,
    min_mentions: int = 1,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> IdeaGraphResponse:
    """Get the user's full Idea Graph with entity nodes and co-occurrence edges."""
    capped_limit = max(1, min(limit, 500))

    query = select(Entity).where(Entity.user_id == user.id, Entity.mention_count >= min_mentions)
    if entity_type:
        normalized = entity_type.strip().lower()
        allowed = {"person", "project", "topic", "place", "organization"}
        if normalized in allowed:
            query = query.where(Entity.entity_type == normalized)

    entities = db.scalars(
        query.order_by(Entity.mention_count.desc(), Entity.last_seen_at.desc()).limit(capped_limit)
    ).all()
    linked_counts: dict[str, int] = {}
    if entities:
        linked_rows = db.execute(
            select(MemoryLink.entity_id, func.count(func.distinct(MemoryLink.session_id)))
            .where(
                MemoryLink.user_id == user.id,
                MemoryLink.entity_id.in_([entity.id for entity in entities]),
                MemoryLink.status != MemoryLinkStatus.rejected.value,
            )
            .group_by(MemoryLink.entity_id)
        ).all()
        linked_counts = {entity_id: int(count) for entity_id, count in linked_rows}

    nodes = [
        EntityResponse(
            entity_id=e.id,
            entity_type=e.entity_type,
            name=e.name,
            mention_count=e.mention_count,
            linked_memory_count=linked_counts.get(e.id, 0),
            first_seen_at=e.first_seen_at,
            last_seen_at=e.last_seen_at,
        )
        for e in entities
    ]

    # Build edges: two entities share an edge if they co-occur in the same session
    entity_ids = [e.id for e in entities]
    edges: list[EntityConnectionResponse] = []

    if len(entity_ids) >= 2:
        # Get all mentions for these entities
        mentions = db.execute(
            select(EntityMention.entity_id, EntityMention.session_id)
            .where(EntityMention.entity_id.in_(entity_ids))
        ).all()

        # Build session->entities mapping
        session_entities: dict[str, set[str]] = {}
        for entity_id, session_id in mentions:
            session_entities.setdefault(session_id, set()).add(entity_id)

        # Build entity lookup
        entity_lookup = {e.id: e for e in entities}

        # Find co-occurrences
        edge_map: dict[tuple[str, str], set[str]] = {}
        for session_id, ent_ids in session_entities.items():
            sorted_ids = sorted(ent_ids)
            for i in range(len(sorted_ids)):
                for j in range(i + 1, len(sorted_ids)):
                    pair = (sorted_ids[i], sorted_ids[j])
                    edge_map.setdefault(pair, set()).add(session_id)

        for (src_id, tgt_id), shared_sessions in edge_map.items():
            src = entity_lookup.get(src_id)
            tgt = entity_lookup.get(tgt_id)
            if src and tgt:
                edges.append(
                    EntityConnectionResponse(
                        source_entity_id=src.id,
                        source_name=src.name,
                        source_type=src.entity_type,
                        target_entity_id=tgt.id,
                        target_name=tgt.name,
                        target_type=tgt.entity_type,
                        shared_session_count=len(shared_sessions),
                        shared_session_ids=sorted(shared_sessions),
                    )
                )

    edges.sort(key=lambda e: e.shared_session_count, reverse=True)

    return IdeaGraphResponse(
        nodes=nodes,
        edges=edges,
        total_entities=len(nodes),
        total_connections=len(edges),
    )


@router.get("/idea-graph/entities/{entity_id}", response_model=EntityResponse)
def get_entity_detail(
    entity_id: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> EntityResponse:
    """Get details for a specific entity."""
    entity = db.scalar(
        select(Entity).where(Entity.id == entity_id, Entity.user_id == user.id)
    )
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")

    linked_memory_count = int(
        db.scalar(
            select(func.count(func.distinct(MemoryLink.session_id))).where(
                MemoryLink.user_id == user.id,
                MemoryLink.entity_id == entity.id,
                MemoryLink.status != MemoryLinkStatus.rejected.value,
            )
        )
        or 0
    )

    return EntityResponse(
        entity_id=entity.id,
        entity_type=entity.entity_type,
        name=entity.name,
        mention_count=entity.mention_count,
        linked_memory_count=linked_memory_count,
        first_seen_at=entity.first_seen_at,
        last_seen_at=entity.last_seen_at,
    )


@router.get("/idea-graph/entities/{entity_id}/mentions", response_model=list[EntityMentionResponse])
def get_entity_mentions(
    entity_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> list[EntityMentionResponse]:
    """Get all session mentions for a specific entity (the 'connections' in the graph)."""
    entity = db.scalar(
        select(Entity).where(Entity.id == entity_id, Entity.user_id == user.id)
    )
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")

    capped = max(1, min(limit, 200))
    mentions = db.scalars(
        select(EntityMention)
        .where(EntityMention.entity_id == entity.id)
        .order_by(EntityMention.created_at.desc())
        .limit(capped)
    ).all()

    return [
        EntityMentionResponse(
            mention_id=m.id,
            entity_id=entity.id,
            entity_name=entity.name,
            entity_type=entity.entity_type,
            session_id=m.session_id,
            context_snippet=m.context_snippet,
            confidence=m.confidence,
            created_at=m.created_at,
        )
        for m in mentions
    ]
