import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.security import decode_stream_access_token
from app.db.session import SessionLocal
from app.models.capture import AudioChunk, CaptureSession, SessionStatus
from app.services.capture_finalize import assemble_capture_session
from app.services.storage import get_storage
from app.utils.crc import crc32_hex
from app.utils.time import utc_now

router = APIRouter(prefix="/stream", tags=["stream"])
settings = get_settings()


def _json_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _send_json(websocket: WebSocket, payload: dict) -> None:
    await websocket.send_text(json.dumps(payload, separators=(",", ":")))


@router.websocket("/ws")
async def websocket_stream(websocket: WebSocket) -> None:
    await websocket.accept()

    token = websocket.query_params.get("stream_token")
    if not token:
        await _send_json(
            websocket,
            {"type": "error", "code": "missing_stream_token", "message": "stream_token query parameter is required"},
        )
        await websocket.close(code=1008)
        return

    claims = decode_stream_access_token(token)
    if not claims:
        await _send_json(websocket, {"type": "error", "code": "invalid_stream_token", "message": "Invalid stream token"})
        await websocket.close(code=1008)
        return

    session_id = str(claims["sub"])
    device_id = str(claims["did"])
    sample_rate = int(claims["sr"])
    channels = int(claims["ch"])
    codec = str(claims["cdc"])
    frame_duration_ms = int(claims["fms"])

    db = SessionLocal()
    try:
        session = db.scalar(
            select(CaptureSession).where(CaptureSession.id == session_id, CaptureSession.device_id == device_id)
        )
        if not session:
            await _send_json(websocket, {"type": "error", "code": "session_not_found", "message": "Session not found"})
            await websocket.close(code=1008)
            return

        if session.status == SessionStatus.done.value:
            await _send_json(
                websocket,
                {"type": "finalized", "session_id": session.id, "status": session.status, "total_chunks": session.total_chunks},
            )
            await websocket.close(code=1000)
            return

        if session.status != SessionStatus.receiving.value:
            await _send_json(
                websocket,
                {"type": "error", "code": "invalid_session_state", "message": f"Session state is {session.status}"},
            )
            await websocket.close(code=1008)
            return

        max_chunk_idx = db.scalar(select(func.max(AudioChunk.chunk_index)).where(AudioChunk.session_id == session.id))
        expected_seq = (max_chunk_idx + 1) if max_chunk_idx is not None else 0

        await _send_json(
            websocket,
            {
                "type": "ready",
                "stream_id": session.id,
                "next_seq": expected_seq,
                "sample_rate": sample_rate,
                "channels": channels,
                "codec": codec,
                "frame_duration_ms": frame_duration_ms,
                "server_time": _json_now(),
            },
        )

        while True:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect:
                return

            message_type = message.get("type")
            if message_type == "websocket.disconnect":
                return

            data = message.get("bytes")
            if data is not None:
                if len(data) < 4:
                    await _send_json(
                        websocket,
                        {"type": "error", "code": "invalid_frame", "message": "Binary frame must include 4-byte sequence header"},
                    )
                    await websocket.close(code=1003)
                    return

                seq = int.from_bytes(data[:4], byteorder="big", signed=False)
                pcm = data[4:]

                if len(pcm) == 0:
                    await _send_json(websocket, {"type": "error", "code": "empty_frame", "message": "Empty PCM payload"})
                    continue

                if len(pcm) > settings.stream_max_frame_bytes:
                    await _send_json(
                        websocket,
                        {
                            "type": "error",
                            "code": "frame_too_large",
                            "message": f"PCM frame exceeds max {settings.stream_max_frame_bytes} bytes",
                        },
                    )
                    continue

                if seq < expected_seq:
                    await _send_json(
                        websocket,
                        {"type": "ack", "ack_seq": expected_seq - 1, "next_seq": expected_seq, "duplicate_seq": seq},
                    )
                    continue

                if seq > expected_seq:
                    await _send_json(websocket, {"type": "nack", "expected_seq": expected_seq, "received_seq": seq})
                    continue

                object_key = f"raw/{session.id}/{seq:06d}.pcm"
                get_storage().put_bytes(object_key, pcm, content_type="application/octet-stream")

                chunk = AudioChunk(
                    session_id=session.id,
                    chunk_index=seq,
                    start_ms=seq * frame_duration_ms,
                    end_ms=(seq + 1) * frame_duration_ms,
                    sample_rate=sample_rate,
                    channels=channels,
                    codec=codec,
                    crc32=crc32_hex(pcm),
                    byte_size=len(pcm),
                    object_key=object_key,
                )
                db.add(chunk)
                session.total_chunks = seq + 1

                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    max_chunk_idx = db.scalar(select(func.max(AudioChunk.chunk_index)).where(AudioChunk.session_id == session.id))
                    expected_seq = (max_chunk_idx + 1) if max_chunk_idx is not None else 0
                    await _send_json(
                        websocket,
                        {"type": "ack", "ack_seq": expected_seq - 1, "next_seq": expected_seq, "duplicate_seq": seq},
                    )
                    continue

                expected_seq += 1
                await _send_json(
                    websocket,
                    {"type": "ack", "ack_seq": expected_seq - 1, "next_seq": expected_seq, "server_time": _json_now()},
                )
                continue

            text_data = message.get("text")
            if text_data is None:
                continue

            try:
                payload = json.loads(text_data)
            except json.JSONDecodeError:
                await _send_json(websocket, {"type": "error", "code": "invalid_json", "message": "Invalid JSON payload"})
                continue

            msg_type = str(payload.get("type", "")).lower()
            if msg_type == "ping":
                await _send_json(websocket, {"type": "pong", "server_time": _json_now()})
                continue

            if msg_type == "end":
                try:
                    total_chunks = assemble_capture_session(db, session)
                except ValueError as exc:
                    await _send_json(websocket, {"type": "error", "code": "empty_session", "message": str(exc)})
                    continue

                await _send_json(
                    websocket,
                    {
                        "type": "finalized",
                        "session_id": session.id,
                        "status": session.status,
                        "total_chunks": total_chunks,
                        "finalized_at": session.finalized_at.isoformat() if session.finalized_at else None,
                    },
                )
                await websocket.close(code=1000)
                return

            if msg_type == "abort":
                reason = str(payload.get("reason") or "aborted_by_device")
                session.status = SessionStatus.failed.value
                session.error_message = reason
                session.finalized_at = utc_now()
                db.commit()
                await _send_json(
                    websocket,
                    {"type": "aborted", "session_id": session.id, "status": session.status, "reason": reason},
                )
                await websocket.close(code=1000)
                return

            await _send_json(
                websocket,
                {"type": "error", "code": "unsupported_message", "message": f"Unsupported message type: {msg_type}"},
            )

    finally:
        db.close()
