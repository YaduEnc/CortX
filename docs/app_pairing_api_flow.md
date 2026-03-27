# App Team API Flow (Pairing + Device Usage)

This document defines the mobile app sequence for user auth, BLE pairing, and paired device retrieval.

## Base URL
- `http://<server-ip>:8000/v1`

## 1) App user signup/login
### Register (development)
`POST /v1/app/register`

Body:
```json
{
  "email": "user@example.com",
  "password": "StrongPass123",
  "full_name": "Demo User"
}
```

### Login
`POST /v1/app/auth`

Body:
```json
{
  "email": "user@example.com",
  "password": "StrongPass123"
}
```

Response (both):
```json
{
  "access_token": "<app_jwt>",
  "token_type": "bearer",
  "expires_in_minutes": 1440
}
```

Use header:
- `Authorization: Bearer <app_jwt>`

## 2) BLE pairing flow
1. Scan BLE devices with pairing service UUID.
2. Connect selected device.
3. Read:
- `device_info` => extract `device_code`
- `pair_nonce`
4. Call backend start pairing:

`POST /v1/pairing/start`

Headers:
- `Authorization: Bearer <app_jwt>`
- `Content-Type: application/json`

Body:
```json
{
  "device_code": "esp32s3-dev-01",
  "pair_nonce": "<nonce_read_from_ble>"
}
```

Response:
```json
{
  "pairing_session_id": "<uuid>",
  "pair_token": "<short_lived_token>",
  "expires_at": "2026-03-25T09:45:00Z"
}
```

5. Write `pair_token` to BLE `pair_token` characteristic.
6. Wait for `pair_status` notify from ESP32.
7. On `success`, refresh paired device list.

## 3) List paired devices
`GET /v1/app/devices`

Headers:
- `Authorization: Bearer <app_jwt>`

Response:
```json
[
  {
    "device_id": "<uuid>",
    "device_code": "esp32s3-dev-01",
    "alias": null,
    "paired_at": "2026-03-25T09:44:30Z"
  }
]
```

## 4) Configure device Wi-Fi (manual/hotspot)
Primary path (works even when device has no internet):
1. Keep BLE connection open after pairing.
2. Write JSON to BLE `wifi_config` characteristic:
```json
{
  "ssid": "UserHotspotOrRouter",
  "password": "secret",
  "persist": true
}
```
3. Observe BLE `wifi_status` notifications:
- `config_received`
- `connecting`
- `connected`
- `saved_not_connected` (saved, but AP not reachable now)

Backend queue fallback (for already paired device):
- `POST /v1/app/devices/{device_id}/network-profile`

Request:
```json
{
  "ssid": "UserHotspotOrRouter",
  "password": "secret",
  "source": "app_manual"
}
```

Response:
```json
{
  "status": "queued",
  "expires_in_seconds": 86400
}
```

## 5) View and play saved audio captures

### List captures
`GET /v1/app/captures?limit=20`

Headers:
- `Authorization: Bearer <app_jwt>`

Returns capture sessions across user-paired devices with status and `has_audio`.

### Play audio
`GET /v1/app/captures/{session_id}/audio`

Headers:
- `Authorization: Bearer <app_jwt>`

Response:
- `audio/wav` bytes (play directly in app)

### View transcript
`GET /v1/app/captures/{session_id}/transcript`

Headers:
- `Authorization: Bearer <app_jwt>`

## Error handling UX
- `404 Device not found`: show "Unknown device"
- `409 Device already paired with another user`: show ownership conflict screen
- `400 Pairing token expired`: auto-retry from BLE read step
- `401 Invalid token`: force app re-login
- `saved_not_connected` wifi status: show "Wi-Fi saved; device will retry when network appears."

## Security notes for app
- Never persist `pair_token` after pairing attempt.
- Keep `app_jwt` in secure storage (Keychain/Keystore).
- If app is backgrounded during pairing, restart from nonce read step.
