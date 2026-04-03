from datetime import datetime, timedelta, timezone
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_app_user
from app.core.config import get_settings
from app.core.security import create_app_access_token, hash_pair_token, hash_secret, verify_secret
from app.db.session import get_db
from app.models.capture import CaptureSession, SessionStatus
from app.models.app_user import AppUser
from app.models.device import Device
from app.models.pairing import DeviceUserBinding, PairingSession
from app.models.password_reset import AppPasswordResetToken
from app.models.transcript import Transcript
from app.services.network_profiles import NETWORK_PROFILE_TTL_SECONDS, queue_network_profile
from app.services.storage import get_storage
from app.schemas.app_user import (
    AppActionStatusResponse,
    AppCaptureListItemResponse,
    AppMeResponse,
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

router = APIRouter(prefix="/app", tags=["app"])


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
    return AppMeResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        created_at=user.created_at,
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

    return [
        PairedDeviceResponse(
            device_id=device.id,
            device_code=device.device_code,
            alias=binding.alias,
            paired_at=binding.paired_at,
        )
        for binding, device in rows
    ]


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


@router.get("/captures", response_model=list[AppCaptureListItemResponse])
def list_user_captures(
    limit: int = 20,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> list[AppCaptureListItemResponse]:
    capped_limit = max(1, min(limit, 100))

    rows = db.execute(
        select(CaptureSession, Device, Transcript)
        .join(Device, Device.id == CaptureSession.device_id)
        .join(
            DeviceUserBinding,
            (DeviceUserBinding.device_id == CaptureSession.device_id)
            & (DeviceUserBinding.user_id == user.id)
            & (DeviceUserBinding.is_active.is_(True)),
        )
        .outerjoin(Transcript, Transcript.session_id == CaptureSession.id)
        .order_by(CaptureSession.started_at.desc())
        .limit(capped_limit)
    ).all()

    return [
        AppCaptureListItemResponse(
            session_id=session.id,
            device_id=device.id,
            device_code=device.device_code,
            status=session.status,
            total_chunks=session.total_chunks,
            started_at=session.started_at,
            finalized_at=session.finalized_at,
            duration_seconds=transcript.duration_seconds if transcript else None,
            has_audio=bool((session.audio_blob_size_bytes or 0) > 0 or session.assembled_object_key),
        )
        for session, device, transcript in rows
    ]


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
        return Response(content=bytes(session.audio_blob_wav), media_type="audio/wav", headers=headers)

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
