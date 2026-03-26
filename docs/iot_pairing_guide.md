# IoT Pairing Guide (ESP32 Team)

This document defines BLE + backend pairing implementation for ESP32.

## Goal
Bind one hardware device to one app user securely before audio upload starts.

## Pairing lifecycle
1. Device enters pairing mode.
Testing option: auto-enter on power-on.
Production option: long-press physical button (5s).
2. Device advertises BLE pairing service for 120s.
3. App reads `device_code` and `pair_nonce` over BLE.
4. App calls backend `POST /v1/pairing/start` with app bearer token.
5. Backend returns short-lived `pair_token`.
6. App writes `pair_token` to BLE characteristic `pair_token`.
7. ESP32 calls backend `POST /v1/device/pairing/complete` using device bearer token.
8. Backend marks device-user binding as paired.
9. ESP32 notifies app over BLE `pair_status=success`.

## BLE GATT contract
Service UUID:
- `SECOND_MIND_PAIR_SERVICE_UUID` (project constant)

Characteristics:
- `device_info` (READ): JSON/text with `device_code`, `fw_version`
- `pair_nonce` (READ): one-time nonce generated when pairing mode starts
- `pair_token` (WRITE): token received from backend via app
- `pair_status` (NOTIFY): `pending|success|failed|expired`

## Nonce rules
- Generate fresh random nonce each pairing window.
- Recommended size: 16+ random bytes, base64/hex encoded.
- Invalidate nonce when pairing window ends.

## Device auth precondition
Device must be registered and authenticated:
- `POST /v1/device/auth` with `device_code + secret`
- Use `Authorization: Bearer <device_jwt>` for `/v1/device/pairing/complete`

## Backend API used by ESP32
### Complete pairing
`POST /v1/device/pairing/complete`

Headers:
- `Authorization: Bearer <DEVICE_JWT>`
- `Content-Type: application/json`

Body:
```json
{
  "pair_token": "<pair_token_from_ble_write>"
}
```

Success response:
```json
{
  "status": "completed",
  "pairing_session_id": "<uuid>",
  "user_id": "<uuid>"
}
```

Failure examples:
- `400 Invalid pairing token`
- `400 Pairing token expired`
- `409 Device already paired with another user`

## ESP32 implementation checklist
- Pairing mode timeout: 120s
- For bench testing without button: auto-pair on boot
- Auto-exit pairing mode on success/failure/timeout
- Clear `pair_token` buffer from RAM after request
- Keep status LED patterns:
  - breathing blue: pairing mode
  - blinking yellow: validating token
  - solid green (2s): success
  - red blink: failed
- Retry backend call up to 3 attempts with backoff (`0.5s`, `1s`, `2s`)

## After pairing success
- Continue normal capture flow from `docs/iot_api_integration.md`
