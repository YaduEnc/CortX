# SecondMind Backend (BLE Phone Gateway)

Production-oriented backend + app gateway foundation for BLE audio capture from ESP32 devices and cloud storage via iOS uplink.

## Tech Stack
- FastAPI (API)
- PostgreSQL (metadata)
- MinIO/S3 (audio storage)
- Redis + Celery (async processing)
- faster-whisper (local STT)
- Docker Compose (local/staging runtime)

## Architecture
1. ESP32 pairs with user (BLE + backend claim flow).
2. ESP32 streams audio packets to iOS over BLE.
3. iOS app starts cloud live stream (`/v1/app/live/start`).
4. iOS app forwards framed PCM over `/v1/stream/ws`.
5. Backend assembles audio and stores final WAV.
6. App fetches captures and plays audio.

## Quick Start
1. Create env file:
```bash
cp .env.example .env
```
2. Start stack:
```bash
docker compose up --build
```
3. API base URL:
```text
http://localhost:8000/v1
```

## API Endpoints
- `GET /v1/health`
- `POST /v1/app/register`
- `POST /v1/app/auth`
- `GET /v1/app/devices`
- `POST /v1/app/live/start`
- `GET /v1/app/captures`
- `GET /v1/app/captures/{session_id}/audio`
- `GET /v1/app/captures/{session_id}/transcript`
- `POST /v1/device/register` (requires `X-Admin-Key`)
- `POST /v1/device/auth`
- `POST /v1/pairing/start`
- `POST /v1/device/pairing/complete`
- `GET /v1/stream/ws?stream_token=...` (websocket)

## IoT Team Guide
Detailed integration contract is documented at:
- `docs/iot_pairing_guide.md`
- `docs/ble_phone_gateway_flow.md`

## App Team Guide
- `docs/app_pairing_api_flow.md`

## Deployment Guide
- `docs/cloudflare_tunnel_deploy_hamza.md`

## Firmware Reference
- `firmware/arduino_ide/SecondMindESP32S3/README_ARDUINO.md`

## Notes
- Raw audio is stored in object storage, not PostgreSQL.
- Database schema currently auto-creates on startup via SQLAlchemy metadata.
- For long-term production, add Alembic migration workflow.
