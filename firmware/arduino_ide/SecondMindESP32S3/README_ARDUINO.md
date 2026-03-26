# Arduino IDE Setup (ESP32-S3 Sense)

1. Open Arduino IDE.
2. Install board package:
   - Boards Manager -> search `esp32` by Espressif Systems -> Install.
3. Select board:
   - `Tools -> Board -> ESP32 Arduino -> XIAO_ESP32S3`.
4. Install library:
   - Library Manager -> `ArduinoJson` by Benoit Blanchon.
5. Recommended Tools options:
   - `USB CDC On Boot -> Enabled` (if available)
   - `PSRAM -> OPI PSRAM` (if available)
   - `Upload Speed -> 921600` (use `115200` if upload is unstable)
5. Open sketch:
   - `firmware/arduino_ide/SecondMindESP32S3/SecondMindESP32S3.ino`
6. Edit config block at top of `SecondMindESP32S3.ino` (single-file setup):
   - Wi-Fi SSID/password
   - `API_BASE_URL`
   - `DEVICE_CODE`, `DEVICE_SECRET`
   - keep mic mode `MIC_MODE_PDM=1`
   - keep XIAO Sense mic pins:
     - `I2S_BCLK_PIN=-1`
     - `I2S_WS_PIN=42`
     - `I2S_DATA_IN_PIN=41`
7. Upload and open Serial Monitor at 115200.
8. Pairing starts automatically on boot (`TEST_MODE_AUTO_PAIR_ON_BOOT=true`).
9. In Serial Monitor, send `r` to trigger one capture session.

Notes:
- Backend must be running at `https://hamza.yaduraj.me/v1`.
- Register device once with backend before flashing.
