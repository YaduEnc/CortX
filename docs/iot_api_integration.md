# IoT API Integration Guide (ESP32 Team)

This guide defines exactly how ESP32 firmware should send audio packets to backend.

Pairing flow is documented separately in `docs/iot_pairing_guide.md`. Complete pairing before starting capture upload.

## Base URL
- Local dev: `http://<server-ip>:8000/v1`

## Auth Flow
### 1) Register Device (one-time, backend/admin operation)
`POST /device/register`

Headers:
- `X-Admin-Key: <ADMIN_BOOTSTRAP_KEY>`
- `Content-Type: application/json`

Body:
```json
{
  "device_code": "esp32s3-dev-01",
  "secret": "very-strong-device-secret"
}
```

### 2) Device Login
`POST /device/auth`

Body:
```json
{
  "device_code": "esp32s3-dev-01",
  "secret": "very-strong-device-secret"
}
```

Response:
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in_minutes": 1440
}
```

Use this header for protected endpoints:
- `Authorization: Bearer <jwt>`

### 3) Pull queued network profile (optional)
`POST /device/network-profile/pull`

Headers:
- `Authorization: Bearer <jwt>`
- `Content-Type: application/json`

Body:
```json
{}
```

Responses:
```json
{
  "status": "none"
}
```
or
```json
{
  "status": "ready",
  "ssid": "UserHotspotOrRouter",
  "password": "secret",
  "source": "app_manual"
}
```

## Session + Chunk Protocol

## Audio format (v1)
- `codec`: `pcm16le`
- `sample_rate`: `16000`
- `channels`: `1`
- chunk duration target: `~2 seconds`

## 1) Create Session
`POST /capture/sessions`

Headers:
- `Authorization: Bearer <jwt>`
- `Content-Type: application/json`

Body:
```json
{
  "sample_rate": 16000,
  "channels": 1,
  "codec": "pcm16le"
}
```

Response:
```json
{
  "session_id": "<uuid>",
  "status": "receiving",
  "started_at": "2026-03-25T08:00:00Z"
}
```

## 2) Upload Chunk
`POST /capture/chunks` (multipart/form-data)

Headers:
- `Authorization: Bearer <jwt>`

Form fields:
- `session_id` (string)
- `chunk_index` (int, starts from 0)
- `start_ms` (int)
- `end_ms` (int)
- `sample_rate` (int)
- `channels` (int)
- `codec` (string)
- `crc32` (optional string, lowercase hex)
- `audio_file` (binary file field)

Expected response:
```json
{
  "session_id": "<uuid>",
  "chunk_index": 0,
  "status": "accepted",
  "next_expected_chunk": 1
}
```

Duplicate re-send returns:
```json
{
  "session_id": "<uuid>",
  "chunk_index": 0,
  "status": "duplicate",
  "next_expected_chunk": 1
}
```

## 3) Finalize Session
`POST /capture/sessions/{session_id}/finalize`

Headers:
- `Authorization: Bearer <jwt>`

Response:
```json
{
  "session_id": "<uuid>",
  "status": "queued"
}
```

## 4) Poll Session Status
`GET /capture/sessions/{session_id}`

Status values:
- `receiving`
- `queued`
- `transcribing`
- `done`
- `failed`

## 5) Fetch Transcript
`GET /capture/sessions/{session_id}/transcript`

Returns transcript text + segments when ready.

## Firmware Reliability Rules
- Maintain local ring buffer for unsent chunks.
- Persist unsent chunks to flash/PSRAM-backed queue if Wi-Fi is unavailable.
- Retries: exponential backoff (`0.5s, 1s, 2s, 4s`, max 5 attempts).
- On timeout/network drop, re-send same `chunk_index`.
- Never skip indices.
- Call finalize only after all chunks have server ack.
- If Wi-Fi cannot connect, keep queue growth bounded and drop oldest chunks after configured storage ceiling.

## CRC32
- Compute CRC32 over raw chunk bytes before upload.
- Send lowercase hex (`08` chars recommended).

## cURL example for chunk
```bash
curl -X POST "http://localhost:8000/v1/capture/chunks" \
  -H "Authorization: Bearer <JWT>" \
  -F "session_id=<SESSION_ID>" \
  -F "chunk_index=0" \
  -F "start_ms=0" \
  -F "end_ms=2000" \
  -F "sample_rate=16000" \
  -F "channels=1" \
  -F "codec=pcm16le" \
  -F "crc32=3f2a1b7c" \
  -F "audio_file=@chunk_000000.pcm;type=application/octet-stream"
```
