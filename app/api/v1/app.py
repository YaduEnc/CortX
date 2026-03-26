from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_app_user
from app.core.config import get_settings
from app.core.security import create_app_access_token, hash_secret, verify_secret
from app.db.session import get_db
from app.models.capture import CaptureSession, SessionStatus
from app.models.app_user import AppUser
from app.models.device import Device
from app.models.pairing import DeviceUserBinding
from app.models.transcript import Transcript
from app.services.storage import get_storage
from app.schemas.app_user import (
    AppCaptureListItemResponse,
    AppCaptureTranscriptResponse,
    AppAuthRequest,
    AppRegisterRequest,
    AppTokenResponse,
    PairedDeviceResponse,
)

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
            has_audio=bool(session.assembled_object_key),
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

    if session.status != SessionStatus.done.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Audio not ready yet")

    if not session.assembled_object_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assembled audio not found")

    audio_bytes = get_storage().get_bytes(session.assembled_object_key)
    headers = {
        "Content-Disposition": f'inline; filename="{session.id}.wav"',
        "Cache-Control": "no-store",
    }
    return Response(content=audio_bytes, media_type="audio/wav", headers=headers)
