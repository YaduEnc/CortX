# SecondMind API Contract Freeze (v1, Updated)

Version: `v1`  
Updated on: `2026-04-01`  
Policy: no breaking payload changes on active v1 routes.

Base URL:
- `https://<domain>/v1`

## 1) App Auth APIs

### POST `/v1/app/register`
Request:
```json
{
  "email": "user@example.com",
  "password": "StrongPass123",
  "full_name": "Demo User"
}
```
Response `201`:
```json
{
  "access_token": "<app_jwt>",
  "token_type": "bearer",
  "expires_in_minutes": 1440
}
```

### POST `/v1/app/auth`
Request:
```json
{
  "email": "user@example.com",
  "password": "StrongPass123"
}
```
Response `200`:
```json
{
  "access_token": "<app_jwt>",
  "token_type": "bearer",
  "expires_in_minutes": 1440
}
```

### GET `/v1/app/me`
Headers:
- `Authorization: Bearer <app_jwt>`

Response `200`:
```json
{
  "user_id": "<uuid>",
  "email": "user@example.com",
  "full_name": "Demo User",
  "created_at": "2026-04-01T08:00:00Z"
}
```

### POST `/v1/app/password/forgot/request`
Request:
```json
{
  "email": "user@example.com"
}
```
Response `200`:
```json
{
  "status": "accepted",
  "message": "If the account exists, a reset token has been issued.",
  "expires_in_seconds": 900,
  "reset_token": "<present_in_non_production_only>"
}
```

### POST `/v1/app/password/forgot/confirm`
Request:
```json
{
  "email": "user@example.com",
  "reset_token": "<token_from_request_step>",
  "new_password": "NewStrongPass123"
}
```
Response `200`:
```json
{
  "status": "password_reset",
  "message": "Password reset successful"
}
```

### POST `/v1/app/me/delete`
Headers:
- `Authorization: Bearer <app_jwt>`

Request:
```json
{
  "password": "CurrentPassword123"
}
```
Response `200`:
```json
{
  "status": "deleted",
  "message": "Account deleted"
}
```

## 2) Pairing APIs

### POST `/v1/pairing/start`
Headers:
- `Authorization: Bearer <app_jwt>`

Request:
```json
{
  "device_code": "manu",
  "pair_nonce": "<nonce_from_ble>"
}
```
Response `200`:
```json
{
  "pairing_session_id": "<uuid>",
  "pair_token": "<short_lived_token>",
  "expires_at": "2026-03-31T10:00:00Z"
}
```

### POST `/v1/device/pairing/complete`
Headers:
- `Authorization: Bearer <device_jwt>`

Request:
```json
{
  "pair_token": "<pair_token_from_app_over_ble>"
}
```
Response `200`:
```json
{
  "status": "completed",
  "pairing_session_id": "<uuid>",
  "user_id": "<uuid>"
}
```

## 3) Live Gateway Start (App-owned)

### POST `/v1/app/live/start`
Headers:
- `Authorization: Bearer <app_jwt>`

Request:
```json
{
  "device_code": "manu",
  "sample_rate": 8000,
  "channels": 1,
  "codec": "pcm16le",
  "frame_duration_ms": 500
}
```
Response `201`:
```json
{
  "session_id": "<uuid>",
  "stream_token": "<jwt>",
  "ws_url": "/v1/stream/ws?stream_token=<jwt>",
  "status": "receiving",
  "sample_rate": 8000,
  "channels": 1,
  "codec": "pcm16le",
  "frame_duration_ms": 500,
  "expires_at": "2026-03-31T10:10:00Z"
}
```

## 4) WebSocket Ingest

### GET `/v1/stream/ws?stream_token=<token>`

Handshake:
- Server sends:
```json
{
  "type": "ready",
  "stream_id": "<uuid>",
  "next_seq": 0,
  "sample_rate": 8000,
  "channels": 1,
  "codec": "pcm16le",
  "frame_duration_ms": 500
}
```

Binary frame format from app:
- first 4 bytes: sequence (big-endian uint32)
- remaining bytes: PCM16LE mono payload

Finalize:
- app sends text message:
```json
{
  "type": "end",
  "reason": "app_stop"
}
```
- server responds:
```json
{
  "type": "finalized",
  "session_id": "<uuid>",
  "status": "done",
  "total_chunks": 10
}
```

## 5) App Capture Retrieval APIs

### GET `/v1/app/captures?limit=20`
Headers:
- `Authorization: Bearer <app_jwt>`

### GET `/v1/app/captures/{session_id}/audio`
Headers:
- `Authorization: Bearer <app_jwt>`

Response:
- Content-Type: `audio/wav`
- Raw WAV bytes

### GET `/v1/app/captures/{session_id}/transcript`
Headers:
- `Authorization: Bearer <app_jwt>`

## Removed / Not Active in Router

These routes are removed from active runtime router:
- `POST /v1/capture/sessions`
- `POST /v1/capture/chunks`
- `POST /v1/capture/sessions/{session_id}/finalize`
- `GET /v1/capture/sessions/{session_id}`
- `GET /v1/capture/sessions/{session_id}/transcript`
- `POST /v1/stream/start` (device-start variant)

## Team handoff docs
- `docs/ble_phone_gateway_flow.md`
- `docs/iot_pairing_guide.md`
- `docs/app_pairing_api_flow.md`
