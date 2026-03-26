import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_app_user, get_current_device
from app.core.config import get_settings
from app.core.security import hash_pair_token
from app.db.session import get_db
from app.models.app_user import AppUser
from app.models.device import Device
from app.models.pairing import DeviceUserBinding, PairingSession
from app.schemas.pairing import (
    PairingCompleteRequest,
    PairingCompleteResponse,
    PairingStartRequest,
    PairingStartResponse,
)
from app.utils.time import utc_now

router = APIRouter(tags=["pairing"])


@router.post("/pairing/start", response_model=PairingStartResponse)
def pairing_start(
    payload: PairingStartRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_app_user),
) -> PairingStartResponse:
    device = db.scalar(select(Device).where(Device.device_code == payload.device_code, Device.is_active.is_(True)))
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    active_binding = db.scalar(
        select(DeviceUserBinding).where(
            DeviceUserBinding.device_id == device.id,
            DeviceUserBinding.is_active.is_(True),
        )
    )
    if active_binding and active_binding.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device already paired with another user")

    if active_binding and active_binding.user_id == user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device already paired with this user")

    now = utc_now()
    pending_sessions = db.scalars(
        select(PairingSession).where(PairingSession.device_id == device.id, PairingSession.status == "pending")
    ).all()
    for session in pending_sessions:
        if session.expires_at <= now:
            session.status = "expired"
        else:
            session.status = "cancelled"

    pair_token = secrets.token_urlsafe(32)
    settings = get_settings()
    expires_at = now + timedelta(seconds=settings.pair_token_ttl_seconds)

    pairing_session = PairingSession(
        device_id=device.id,
        user_id=user.id,
        pair_nonce=payload.pair_nonce,
        pair_token_hash=hash_pair_token(pair_token),
        status="pending",
        expires_at=expires_at,
    )
    db.add(pairing_session)
    db.commit()
    db.refresh(pairing_session)

    return PairingStartResponse(
        pairing_session_id=pairing_session.id,
        pair_token=pair_token,
        expires_at=pairing_session.expires_at,
    )


@router.post("/device/pairing/complete", response_model=PairingCompleteResponse)
def pairing_complete(
    payload: PairingCompleteRequest,
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> PairingCompleteResponse:
    now = utc_now()

    session = db.scalar(
        select(PairingSession)
        .where(
            PairingSession.device_id == device.id,
            PairingSession.pair_token_hash == hash_pair_token(payload.pair_token),
        )
        .order_by(PairingSession.created_at.desc())
    )

    if not session:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pairing token")

    if session.status != "pending":
        if session.status == "completed":
            return PairingCompleteResponse(status="completed", pairing_session_id=session.id, user_id=session.user_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Pairing session is {session.status}")

    if session.expires_at <= now:
        session.status = "expired"
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pairing token expired")

    binding = db.scalar(select(DeviceUserBinding).where(DeviceUserBinding.device_id == device.id))
    if binding and binding.user_id != session.user_id and binding.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device already paired with another user")

    if not binding:
        binding = DeviceUserBinding(device_id=device.id, user_id=session.user_id, is_active=True)
        db.add(binding)
    else:
        binding.user_id = session.user_id
        binding.is_active = True

    session.status = "completed"
    session.completed_at = now
    db.commit()

    return PairingCompleteResponse(status="completed", pairing_session_id=session.id, user_id=session.user_id)
