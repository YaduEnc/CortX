#pragma once

// Wi-Fi
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// Backend
// Keep NO trailing slash.
#define API_BASE_URL "https://hamza.yaduraj.me/v1"

// Device credentials (created via POST /v1/device/register)
#define DEVICE_CODE "manu"
#define DEVICE_SECRET "1234567890"

// Device identity visible in BLE
#define DEVICE_BLE_NAME "SecondMind"

// GPIO
// Set to -1 to disable hardware pairing button in testing.
#define PAIR_BUTTON_PIN -1

// Mic profile
// 1 = onboard PDM mic profile (ESP32-S3 Sense style)
// 0 = external standard I2S mic profile
#define MIC_MODE_PDM 1

// Seeed XIAO ESP32S3 Sense onboard PDM mic pins:
// GPIO41 = DATA, GPIO42 = CLK
// In this driver path, use WS as PDM clock and DATA_IN as microphone data.
#define I2S_BCLK_PIN -1
#define I2S_WS_PIN 42
#define I2S_DATA_IN_PIN 41

// Audio
#define SAMPLE_RATE_HZ 16000
#define SAMPLE_BITS 16
#define CHANNELS 1
#define CHUNK_DURATION_MS 2000
#define CAPTURE_CHUNKS_PER_SESSION 3

// Testing mode
// When true and device is not paired, pairing mode starts automatically on boot.
#define TEST_MODE_AUTO_PAIR_ON_BOOT true
