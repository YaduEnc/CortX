# SecondMind API Contract Freeze (v1)

Version: `v1`
Freeze date: `2026-03-25`
Change policy: No payload changes without introducing new versioned route or additive optional fields only.

Base URL:
- `http://<server-ip>:8000/v1`

## Contract rules
- Keep existing field names/types unchanged.
- New required fields are not allowed in v1.
- Only additive optional fields are allowed.
- Breaking changes require `v2` routes.

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

## 2) Pairing APIs

### POST `/v1/pairing/start`
Headers:
- `Authorization: Bearer <app_jwt>`

Request:
```json
{
  "device_code": "esp32s3-dev-01",
  "pair_nonce": "<nonce_from_ble>"
}
```
Response `200`:
```json
{
  "pairing_session_id": "<uuid>",
  "pair_token": "<short_lived_token>",
  "expires_at": "2026-03-25T09:45:00Z"
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

### POST `/v1/app/devices/{device_id}/network-profile`
Headers:
- `Authorization: Bearer <app_jwt>`

Request:
```json
{
  "ssid": "UserHotspotOrRouter",
  "password": "secret",
  "source": "app_manual"
}
```

Response `200`:
```json
{
  "status": "queued",
  "expires_in_seconds": 86400
}
```

### POST `/v1/device/network-profile/pull`
Headers:
- `Authorization: Bearer <device_jwt>`

Request:
```json
{}
```

Response `200` (none):
```json
{
  "status": "none"
}
```

Response `200` (ready):
```json
{
  "status": "ready",
  "ssid": "UserHotspotOrRouter",
  "password": "secret",
  "source": "app_manual"
}
```

## 3) Capture APIs

### POST `/v1/capture/sessions`
Headers:
- `Authorization: Bearer <device_jwt>`

Request:
```json
{
  "sample_rate": 16000,
  "channels": 1,
  "codec": "pcm16le"
}
```
Response `201`:
```json
{
  "session_id": "<uuid>",
  "status": "receiving",
  "started_at": "2026-03-25T08:00:00Z"
}
```

### POST `/v1/capture/chunks`
Headers:
- `Authorization: Bearer <device_jwt>`
- `Content-Type: multipart/form-data`

Form fields:
- `session_id` string
- `chunk_index` int
- `start_ms` int
- `end_ms` int
- `sample_rate` int
- `channels` int
- `codec` string
- `crc32` optional string
- `audio_file` binary

Response `200` (accepted):
```json
{
  "session_id": "<uuid>",
  "chunk_index": 0,
  "status": "accepted",
  "next_expected_chunk": 1
}
```
Response `200` (duplicate):
```json
{
  "session_id": "<uuid>",
  "chunk_index": 0,
  "status": "duplicate",
  "next_expected_chunk": 1
}
```

### POST `/v1/capture/sessions/{session_id}/finalize`
Headers:
- `Authorization: Bearer <device_jwt>`

Response `200`:
```json
{
  "session_id": "<uuid>",
  "status": "queued"
}
```

### GET `/v1/capture/sessions/{session_id}`
Headers:
- `Authorization: Bearer <device_jwt>`

Response `200`:
```json
{
  "session_id": "<uuid>",
  "status": "transcribing",
  "total_chunks": 12,
  "error_message": null,
  "started_at": "2026-03-25T08:00:00Z",
  "finalized_at": "2026-03-25T08:02:00Z"
}
```

### GET `/v1/capture/sessions/{session_id}/transcript`
Headers:
- `Authorization: Bearer <device_jwt>`

Response `200`:
```json
{
  "session_id": "<uuid>",
  "model_name": "small",
  "language": "en",
  "full_text": "Hello world",
  "duration_seconds": 8.4,
  "segments": [
    {
      "segment_index": 0,
      "start_seconds": 0.0,
      "end_seconds": 2.3,
      "text": "Hello"
    }
  ]
}
```

## 4) App Capture Retrieval APIs

### GET `/v1/app/captures?limit=20`
Headers:
- `Authorization: Bearer <app_jwt>`

Response `200`:
```json
[
  {
    "session_id": "<uuid>",
    "device_id": "<uuid>",
    "device_code": "esp32s3-dev-01",
    "status": "done",
    "total_chunks": 12,
    "started_at": "2026-03-25T08:00:00Z",
    "finalized_at": "2026-03-25T08:02:00Z",
    "duration_seconds": 8.4,
    "has_audio": true
  }
]
```

### GET `/v1/app/captures/{session_id}/audio`
Headers:
- `Authorization: Bearer <app_jwt>`

Response `200`:
- Content-Type: `audio/wav`
- Raw WAV bytes

Error examples:
- `409 Audio not ready yet`
- `404 Assembled audio not found`

### GET `/v1/app/captures/{session_id}/transcript`
Headers:
- `Authorization: Bearer <app_jwt>`

Response `200`:
```json
{
  "session_id": "<uuid>",
  "model_name": "small",
  "language": "en",
  "full_text": "Hello world",
  "duration_seconds": 8.4
}
```

## Team handoff docs
- App team: `docs/app_pairing_api_flow.md`
- IoT pairing: `docs/iot_pairing_guide.md`
- IoT capture upload: `docs/iot_api_integration.md`
