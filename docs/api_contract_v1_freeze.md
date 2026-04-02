# SecondMind API Contract Freeze (v1, Active Routes)

Version: `v1`  
Updated on: `2026-04-03`  
Policy: no breaking payload changes on active v1 routes.

Base URL:
- `https://<domain>/v1`

## Health

### GET `/v1/health`
Response `200`:
```json
{
  "status": "ok"
}
```

## 1) App Auth and Account APIs

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
  "created_at": "2026-04-03T08:00:00Z"
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
  "expires_at": "2026-04-03T10:00:00Z"
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

### GET `/v1/app/devices`
Headers:
- `Authorization: Bearer <app_jwt>`

Response `200`:
```json
[
  {
    "device_id": "<uuid>",
    "device_code": "manu",
    "alias": null,
    "paired_at": "2026-04-03T10:05:00Z"
  }
]
```

## 3) Device Auth and Capture APIs

### POST `/v1/device/register`
Headers:
- `X-Admin-Key: <admin_bootstrap_key>`

Request:
```json
{
  "device_code": "manu",
  "secret": "6109994804"
}
```
Response `201`:
```json
{
  "id": "<uuid>",
  "device_code": "manu",
  "is_active": true
}
```

### POST `/v1/device/auth`
Request:
```json
{
  "device_code": "manu",
  "secret": "6109994804"
}
```
Response `200`:
```json
{
  "access_token": "<device_jwt>",
  "token_type": "bearer",
  "expires_in_minutes": 1440
}
```

### POST `/v1/device/captures/upload-wav`
Headers:
- `Authorization: Bearer <device_jwt>`
- `Content-Type: audio/wav`
- `X-Sample-Rate: 16000` (8000..48000)
- `X-Channels: 1` (1..2)
- `X-Codec: pcm16le`

Body:
- raw WAV bytes

Response `201`:
```json
{
  "session_id": "<uuid>",
  "status": "queued",
  "queued_for_transcription": true,
  "audio_size_bytes": 160044,
  "sample_rate": 16000,
  "channels": 1,
  "codec": "pcm16le"
}
```

## 4) Network Profile APIs

### POST `/v1/app/devices/{device_id}/network-profile`
Headers:
- `Authorization: Bearer <app_jwt>`

Request:
```json
{
  "ssid": "MyWiFi",
  "password": "secret1234",
  "source": "app_manual"
}
```
Response `200`:
```json
{
  "status": "queued",
  "expires_in_seconds": 300
}
```

### POST `/v1/device/network-profile/pull`
Headers:
- `Authorization: Bearer <device_jwt>`

Response `200` (when available):
```json
{
  "status": "ready",
  "ssid": "MyWiFi",
  "password": "secret1234",
  "source": "app_manual"
}
```

Response `200` (when none queued):
```json
{
  "status": "none"
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

## Deprecated Compatibility Endpoint

### POST `/v1/app/live/start`
Headers:
- `Authorization: Bearer <app_jwt>`

Current behavior:
- Returns `410 Gone`
- Detail: `"Live packet streaming is deprecated. Use device direct upload /v1/device/captures/upload-wav."`

## Not in Active Contract

The following flows are intentionally excluded from the active v1 contract:
- WebSocket streaming ingest (`/v1/stream/ws`)
- legacy chunk/session capture ingest routes
- ad-hoc/experimental command detection routes
