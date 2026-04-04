from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_device
from app.core.config import get_settings
from app.core.security import create_device_access_token, hash_secret, verify_secret
from app.db.session import get_db
from app.models.capture import AudioChunk, CaptureSession, SessionStatus
from app.models.device import Device
from app.models.pairing import DeviceUserBinding
from app.schemas.device import (
    DeviceAuthRequest,
    DeviceCaptureChunkUploadResponse,
    DeviceCaptureFinalizeRequest,
    DeviceCaptureFinalizeResponse,
    DevicePairingStatusResponse,
    DeviceHeartbeatRequest,
    DeviceHeartbeatResponse,
    DeviceCaptureSessionStartRequest,
    DeviceCaptureSessionStartResponse,
    DeviceCaptureUploadResponse,
    DeviceRegisterRequest,
    DeviceResponse,
    TokenResponse,
)
from app.schemas.network import DeviceNetworkProfilePullResponse
from app.services.capture_finalize import assemble_capture_session
from app.services.network_profiles import consume_network_profile
from app.utils.crc import crc32_hex
from app.utils.time import utc_now
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/device", tags=["device"])


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

    device.last_seen_at = utc_now()
    db.commit()

    token = create_device_access_token(device.id)
    settings = get_settings()
    return TokenResponse(access_token=token, expires_in_minutes=settings.jwt_expires_minutes)


@router.get("/pairing/status", response_model=DevicePairingStatusResponse)
def get_device_pairing_status(
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> DevicePairingStatusResponse:
    binding = db.scalar(
        select(DeviceUserBinding).where(
            DeviceUserBinding.device_id == device.id,
            DeviceUserBinding.is_active.is_(True),
        )
    )

    device.last_seen_at = utc_now()
    db.commit()

    return DevicePairingStatusResponse(
        status="paired" if binding else "unpaired",
        device_id=device.id,
        device_code=device.device_code,
        is_paired=binding is not None,
        paired_at=binding.paired_at if binding else None,
        user_id=binding.user_id if binding else None,
    )


@router.post("/network-profile/pull", response_model=DeviceNetworkProfilePullResponse)
def pull_network_profile(db: Session = Depends(get_db), device: Device = Depends(get_current_device)) -> DeviceNetworkProfilePullResponse:
    device.last_seen_at = utc_now()
    db.commit()

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


@router.post("/capture/sessions", response_model=DeviceCaptureSessionStartResponse, status_code=status.HTTP_201_CREATED)
def start_capture_session(
    payload: DeviceCaptureSessionStartRequest,
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> DeviceCaptureSessionStartResponse:
    codec = payload.codec.strip().lower()
    if not codec:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="codec is required")

    session = CaptureSession(
        device_id=device.id,
        status=SessionStatus.receiving.value,
        sample_rate=payload.sample_rate,
        channels=payload.channels,
        codec=codec,
        total_chunks=0,
    )
    device.last_seen_at = utc_now()
    db.add(session)
    db.commit()
    db.refresh(session)

    return DeviceCaptureSessionStartResponse(
        session_id=session.id,
        status=session.status,
        sample_rate=session.sample_rate,
        channels=session.channels,
        codec=session.codec,
    )


@router.post("/capture/chunks", response_model=DeviceCaptureChunkUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_capture_chunk(
    chunk_bytes: bytes = Body(..., media_type="application/octet-stream"),
    x_session_id: str = Header(...),
    x_chunk_index: int = Header(...),
    x_start_ms: int = Header(...),
    x_end_ms: int = Header(...),
    x_sample_rate: int = Header(default=16000),
    x_channels: int = Header(default=1),
    x_codec: str = Header(default="pcm16le"),
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> DeviceCaptureChunkUploadResponse:
    settings = get_settings()
    if len(chunk_bytes) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chunk payload is empty")
    if len(chunk_bytes) > settings.max_chunk_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Chunk exceeds max {settings.max_chunk_bytes} bytes",
        )
    if x_chunk_index < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Chunk-Index must be >= 0")
    if x_end_ms <= x_start_ms:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-End-Ms must be greater than X-Start-Ms")

    session = db.scalar(
        select(CaptureSession).where(CaptureSession.id == x_session_id, CaptureSession.device_id == device.id)
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capture session not found")
    if session.status != SessionStatus.receiving.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Session state is {session.status}")

    max_chunk_idx = db.scalar(select(func.max(AudioChunk.chunk_index)).where(AudioChunk.session_id == session.id))
    expected_seq = (max_chunk_idx + 1) if max_chunk_idx is not None else 0

    if x_chunk_index < expected_seq:
        return DeviceCaptureChunkUploadResponse(
            session_id=session.id,
            chunk_index=x_chunk_index,
            status="duplicate",
            ack_seq=expected_seq - 1,
            next_seq=expected_seq,
            total_chunks=session.total_chunks,
            byte_size=len(chunk_bytes),
        )
    if x_chunk_index > expected_seq:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Out-of-order chunk. expected={expected_seq} received={x_chunk_index}",
        )

    chunk = AudioChunk(
        session_id=session.id,
        chunk_index=x_chunk_index,
        start_ms=x_start_ms,
        end_ms=x_end_ms,
        sample_rate=x_sample_rate,
        channels=x_channels,
        codec=x_codec.strip().lower() or "pcm16le",
        crc32=crc32_hex(chunk_bytes),
        byte_size=len(chunk_bytes),
        object_key=None,
        pcm_data=chunk_bytes,
    )
    db.add(chunk)
    session.total_chunks = x_chunk_index + 1
    device.last_seen_at = utc_now()

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        max_chunk_idx = db.scalar(select(func.max(AudioChunk.chunk_index)).where(AudioChunk.session_id == session.id))
        expected_seq = (max_chunk_idx + 1) if max_chunk_idx is not None else 0
        return DeviceCaptureChunkUploadResponse(
            session_id=session.id,
            chunk_index=x_chunk_index,
            status="duplicate",
            ack_seq=expected_seq - 1,
            next_seq=expected_seq,
            total_chunks=session.total_chunks,
            byte_size=len(chunk_bytes),
        )

    return DeviceCaptureChunkUploadResponse(
        session_id=session.id,
        chunk_index=x_chunk_index,
        status="stored",
        ack_seq=x_chunk_index,
        next_seq=x_chunk_index + 1,
        total_chunks=session.total_chunks,
        byte_size=len(chunk_bytes),
    )


@router.post("/capture/sessions/{session_id}/finalize", response_model=DeviceCaptureFinalizeResponse)
def finalize_capture_session(
    session_id: str,
    payload: DeviceCaptureFinalizeRequest,
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> DeviceCaptureFinalizeResponse:
    device.last_seen_at = utc_now()

    session = db.scalar(
        select(CaptureSession).where(CaptureSession.id == session_id, CaptureSession.device_id == device.id)
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capture session not found")

    if session.status in {
        SessionStatus.queued.value,
        SessionStatus.transcribing.value,
        SessionStatus.done.value,
    }:
        return DeviceCaptureFinalizeResponse(
            session_id=session.id,
            status=session.status,
            total_chunks=session.total_chunks,
            queued_for_transcription=session.status in {SessionStatus.queued.value, SessionStatus.transcribing.value},
        )
    if session.status != SessionStatus.receiving.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Session state is {session.status}")

    if payload.reason:
        session.error_message = payload.reason.strip()[:255]

    try:
        total_chunks = assemble_capture_session(db, session)
    except ValueError as exc:
        if str(exc) == "Cannot finalize empty session":
            session.status = SessionStatus.failed.value
            session.total_chunks = 0
            if not session.error_message:
                session.error_message = "empty_session"
            session.finalized_at = utc_now()
            db.commit()
            db.refresh(session)
            return DeviceCaptureFinalizeResponse(
                session_id=session.id,
                status=session.status,
                total_chunks=0,
                queued_for_transcription=False,
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _enqueue_transcription(session, db)

    return DeviceCaptureFinalizeResponse(
        session_id=session.id,
        status=session.status,
        total_chunks=total_chunks,
        queued_for_transcription=True,
    )


@router.post("/captures/upload-wav", response_model=DeviceCaptureUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_device_capture_wav(
    wav_bytes: bytes = Body(..., media_type="audio/wav"),
    x_sample_rate: int = Header(default=16000),
    x_channels: int = Header(default=1),
    x_codec: str = Header(default="pcm16le"),
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> DeviceCaptureUploadResponse:
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
    device.last_seen_at = utc_now()
    db.add(session)
    db.commit()
    db.refresh(session)

    _enqueue_transcription(session, db)

    return DeviceCaptureUploadResponse(
        session_id=session.id,
        status=session.status,
        queued_for_transcription=True,
        audio_size_bytes=len(wav_bytes),
        sample_rate=session.sample_rate,
        channels=session.channels,
        codec=session.codec,
    )


@router.post("/heartbeat", response_model=DeviceHeartbeatResponse)
def device_heartbeat(
    payload: DeviceHeartbeatRequest,
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> DeviceHeartbeatResponse:
    now = utc_now()
    device.last_seen_at = now
    if payload.firmware_version is not None:
        fw = payload.firmware_version.strip()
        device.firmware_version = fw or None
    db.commit()
    db.refresh(device)

    return DeviceHeartbeatResponse(
        status="ok",
        device_id=device.id,
        last_seen_at=device.last_seen_at or now,
        firmware_version=device.firmware_version,
    )
