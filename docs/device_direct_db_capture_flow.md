# Device Direct Capture -> Backend DB Flow

This flow removes Supabase object storage from the ESP32 recorder path.

## Runtime sequence

1. Device authenticates:
   - `POST /v1/device/auth`
2. Device records WAV locally.
3. Device uploads WAV bytes to backend:
   - `POST /v1/device/captures/upload-wav`
   - headers:
     - `Authorization: Bearer <device_jwt>`
     - `Content-Type: audio/wav`
     - `X-Sample-Rate: 16000`
     - `X-Channels: 1`
     - `X-Codec: pcm16le`
4. Backend writes WAV bytes into `capture_sessions.audio_blob_wav` (`bytea`) and sets status `queued`.
5. Backend enqueues Celery transcription task.
6. Worker transcribes with faster-whisper and stores transcript in `transcripts` + `transcript_segments`.
7. App consumes captures via existing APIs:
   - `GET /v1/app/captures`
   - `GET /v1/app/captures/{session_id}/audio`
   - `GET /v1/app/captures/{session_id}/transcript`

## New endpoint response

`POST /v1/device/captures/upload-wav` returns:

```json
{
  "session_id": "uuid",
  "status": "queued",
  "queued_for_transcription": true,
  "audio_size_bytes": 160044,
  "sample_rate": 16000,
  "channels": 1,
  "codec": "pcm16le"
}
```

## Migration for existing DBs

Run:
- `docs/postgres_audio_storage_migration.sql`

## Firmware

Use the sketch at:
- `firmware/arduino_ide/SecondMindESP32S3BackendDB/SecondMindESP32S3BackendDB.ino`
