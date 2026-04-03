# SecondMind Backend (Device Direct DB Upload)

Production-oriented backend + app pairing foundation for ESP32 device direct WAV upload into PostgreSQL and app playback.

## Tech Stack
- FastAPI (API)
- PostgreSQL (metadata)
- MinIO/S3 (audio storage)
- Redis + Celery (async processing)
- faster-whisper (local STT)
- Docker Compose (local/staging runtime)

## Architecture
1. ESP32 pairs with user (BLE + backend claim flow).
2. ESP32 records one WAV session on wake/stop trigger.
3. ESP32 uploads WAV directly to backend (`/v1/device/captures/upload-wav`).
4. Backend stores WAV in PostgreSQL (`bytea`) and queues transcription.
5. App fetches captures and plays audio from API (`/v1/app/captures/{id}/audio`).

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
- `GET /v1/app/captures`
- `GET /v1/app/captures/{session_id}/audio`
- `GET /v1/app/captures/{session_id}/transcript`
- `POST /v1/device/register` (requires `X-Admin-Key`)
- `POST /v1/device/auth`
- `POST /v1/device/captures/upload-wav` (device bearer token; stores WAV in PostgreSQL)
- `POST /v1/pairing/start`
- `POST /v1/device/pairing/complete`
- `POST /v1/app/live/start` (deprecated, returns 410)

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
- Raw/assembled audio is now persisted in PostgreSQL (`bytea`) for DB-first capture flows.
- Database schema currently auto-creates on startup via SQLAlchemy metadata.
- For long-term production, add Alembic migration workflow.
