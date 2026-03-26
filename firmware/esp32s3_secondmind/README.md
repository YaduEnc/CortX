# ESP32-S3 Firmware (SecondMind)

Reference firmware implementing:
- BLE pairing handshake with app
- Device auth with backend
- Audio chunk capture and upload (`pcm16le`, 16kHz)
- Session finalize API call

## Files
- `platformio.ini`
- `include/config.h`
- `src/main.cpp`

## 1) Configure
Edit `include/config.h`:
- `WIFI_SSID`, `WIFI_PASSWORD`
- `API_BASE_URL` (example: `https://hamza.yaduraj.me/v1`)
- `DEVICE_CODE`, `DEVICE_SECRET`
- `MIC_MODE_PDM=1` for ESP32-S3-Sense onboard mic profile
- onboard mic pins (default now): `BCLK=41`, `WS=-1`, `DATA_IN=42`
- `PAIR_BUTTON_PIN=-1` for no physical button
- `TEST_MODE_AUTO_PAIR_ON_BOOT=true` for instant pairing mode on power-on

## 2) Build and flash
```bash
cd /Users/sujeetkumarsingh/Desktop/CortX/firmware/esp32s3_secondmind
pio run
pio run -t upload
pio device monitor
```

## 3) Pairing flow
1. If `TEST_MODE_AUTO_PAIR_ON_BOOT=true`, pairing mode starts automatically after power-on.
2. If auto mode is false, long-press pairing button (`PAIR_BUTTON_PIN`) for 5s.
3. App scans BLE service and reads `device_code` + `pair_nonce`.
4. App calls `POST /v1/pairing/start` and gets `pair_token`.
5. App writes `pair_token` into BLE `pair_token` characteristic.
6. ESP32 calls `POST /v1/device/pairing/complete`.
7. Pair status notifies over BLE.

## 4) Capture test
- Serial command `r` runs one capture session:
  - `POST /v1/capture/sessions`
  - `POST /v1/capture/chunks`
  - `POST /v1/capture/sessions/{id}/finalize`

## BLE UUIDs in firmware
- Service: `8b6ad1ca-c85d-4262-b1f6-85e134fdb2f0`
- `device_info`: `94dcbd89-0f5a-4fb3-9f61-a3d2664d35d1`
- `pair_nonce`: `2dc45f2c-5924-48cf-a615-f9e3c1070ad4`
- `pair_token`: `9f8b48ad-e983-4abf-8b56-53f31c0f7596`
- `pair_status`: `ea85f9b1-1c57-4fdd-95ac-5c92b8a07b3d`

## Important notes
- Firmware uses `client.setInsecure()` for HTTPS simplicity. Replace with cert pinning for production.
- `config.h` currently contains placeholders. Set real values before flashing.
- If your Sense board revision uses different onboard mic pins, update `I2S_BCLK_PIN` and `I2S_DATA_IN_PIN`.
- Backend does not need changes for onboard mic; API stays the same.
