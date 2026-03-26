# SecondMind Backend (Phase 1)

Production-oriented backend foundation for audio capture from ESP32 devices, local transcription with Whisper, and transcript retrieval APIs.

## Tech Stack
- FastAPI (API)
- PostgreSQL (metadata)
- MinIO/S3 (audio storage)
- Redis + Celery (async processing)
- faster-whisper (local STT)
- Docker Compose (local/staging runtime)

## Architecture
1. ESP32 authenticates and receives JWT.
2. ESP32 creates a capture session.
3. ESP32 uploads sequential audio chunks (`pcm16le`, 16kHz recommended).
4. Device finalizes session.
5. Worker assembles chunks, runs local Whisper, stores transcript.
6. App/clients fetch session status and transcript.

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
- `POST /v1/device/register` (requires `X-Admin-Key`)
- `POST /v1/device/auth`
- `POST /v1/pairing/start`
- `POST /v1/device/pairing/complete`
- `POST /v1/capture/sessions`
- `POST /v1/capture/chunks`
- `POST /v1/capture/sessions/{session_id}/finalize`
- `GET /v1/capture/sessions/{session_id}`
- `GET /v1/capture/sessions/{session_id}/transcript`

## IoT Team Guide
Detailed integration contract is documented at:
- `docs/iot_api_integration.md`
- `docs/iot_pairing_guide.md`

## App Team Guide
- `docs/app_pairing_api_flow.md`

## Deployment Guide
- `docs/cloudflare_tunnel_deploy_hamza.md`

## Firmware Reference
- `firmware/esp32s3_secondmind/README.md`

## Notes
- Raw audio is stored in object storage, not PostgreSQL.
- Database schema currently auto-creates on startup via SQLAlchemy metadata.
- For long-term production, add Alembic migration workflow.
