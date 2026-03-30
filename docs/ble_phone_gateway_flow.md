# SecondMind BLE Phone Gateway Flow (v1)

This flow replaces direct ESP internet upload.

Data path:

`ESP32 -> BLE notifications -> iOS app -> backend websocket`

## 1) BLE Service + Characteristics

Service UUID:

- `8b6ad1ca-c85d-4262-b1f6-85e134fdb2f0`

Existing pairing chars remain unchanged.

New audio chars:

- `audio_control` (WRITE): `start` / `stop`
  - UUID: `d413d6c7-2d5f-4f04-8dd1-d0cd9cbdc1f1`
- `audio_data` (NOTIFY): binary packet
  - UUID: `8f7f3b93-9b0f-4fcb-8a0c-0e7f4e4fd2d1`
- `audio_state` (READ/NOTIFY): `idle|capturing|error`
  - UUID: `5e0f6d5f-cf6e-4dc5-9fca-2fa2a3434f4a`

## 2) BLE Audio Packet Format

Binary payload in `audio_data` notify:

- bytes `[0..3]`: `seq` (uint32, big-endian)
- bytes `[4..]`: PCM16LE mono audio chunk

Current firmware settings:

- sample rate: `8000`
- channels: `1`
- packet PCM bytes: `160` (10 ms at 8kHz mono 16-bit)

## 3) App -> Backend Live Start

Endpoint:

- `POST /v1/app/live/start` (app bearer token required)

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

Response returns:

- `session_id`
- `stream_token`
- `ws_url` (`/v1/stream/ws?stream_token=...`)

## 4) App WebSocket Uplink

The app opens `wss://.../v1/stream/ws?stream_token=...` and:

- accumulates BLE PCM until one frame (`frame_duration_ms`)
- sends WS binary frame:
  - first 4 bytes: stream `seq` big-endian
  - rest: PCM frame bytes
- on stop:
  - app sends BLE `stop`
  - app sends WS control JSON:
    - `{"type":"end","reason":"app_stop"}`

## 5) Current UI Flow

Dashboard now has **Live Gateway** card:

- Start Live: starts app live stream + BLE autoconnect + sends BLE `start`
- Stop Live: sends BLE `stop`, sends WS `end`
- Metrics shown:
  - uploaded frames
  - received BLE packets
  - estimated BLE packet drops

