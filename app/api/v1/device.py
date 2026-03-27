from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_device
from app.core.config import get_settings
from app.core.security import create_device_access_token, hash_secret, verify_secret
from app.db.session import get_db
from app.models.device import Device
from app.schemas.device import DeviceAuthRequest, DeviceRegisterRequest, DeviceResponse, TokenResponse
from app.schemas.network import DeviceNetworkProfilePullResponse
from app.services.network_profiles import consume_network_profile

router = APIRouter(prefix="/device", tags=["device"])


@router.post("/register", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
def register_device(
    payload: DeviceRegisterRequest,
    db: Session = Depends(get_db),
    x_admin_key: str | None = Header(default=None),
) -> DeviceResponse:
    settings = get_settings()
    if x_admin_key != settings.admin_bootstrap_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key")

    existing = db.scalar(select(Device).where(Device.device_code == payload.device_code))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device code already exists")

    device = Device(device_code=payload.device_code, secret_hash=hash_secret(payload.secret))
    db.add(device)
    db.commit()
    db.refresh(device)

    return DeviceResponse(id=device.id, device_code=device.device_code, is_active=device.is_active)


@router.post("/auth", response_model=TokenResponse)
def authenticate_device(payload: DeviceAuthRequest, db: Session = Depends(get_db)) -> TokenResponse:
    device = db.scalar(select(Device).where(Device.device_code == payload.device_code))
    if not device or not verify_secret(payload.secret, device.secret_hash) or not device.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_device_access_token(device.id)
    settings = get_settings()
    return TokenResponse(access_token=token, expires_in_minutes=settings.jwt_expires_minutes)


@router.post("/network-profile/pull", response_model=DeviceNetworkProfilePullResponse)
def pull_network_profile(device: Device = Depends(get_current_device)) -> DeviceNetworkProfilePullResponse:
    profile = consume_network_profile(device.id)
    if not profile:
        return DeviceNetworkProfilePullResponse(status="none")

    ssid = str(profile.get("ssid") or "").strip()
    if not ssid:
        return DeviceNetworkProfilePullResponse(status="none")

    return DeviceNetworkProfilePullResponse(
        status="ready",
        ssid=ssid,
        password=str(profile.get("password") or ""),
        source=str(profile.get("source") or "app_manual"),
    )
