/*
 * =====================================================================
 *  ESP32-S3 Sense — Backend DB Audio Upload + BLE Pairing
 * =====================================================================
 *  Board  : XIAO ESP32S3 Sense
 *  Tools  : PSRAM -> OPI PSRAM (required)
 *  Library: ArduinoJson by Benoit Blanchon
 *
 *  Flow:
 *    1) Device authenticates with backend (/v1/device/auth)
 *    2) Device can enter BLE pairing mode (serial command: p)
 *    3) App writes pair token over BLE
 *    4) Device completes pairing with backend (/v1/device/pairing/complete)
 *    5) Device detects wake/stop phrases on-device (DTW template matcher)
 *    6) Device records one WAV session and uploads to backend DB (/v1/device/captures/upload-wav)
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <driver/i2s_pdm.h>
#include <driver/i2s_common.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <Preferences.h>
#include <esp_system.h>
#include <ctype.h>
#include <float.h>

// ---------------------------------------------------------------------
// USER CONFIG
// ---------------------------------------------------------------------
const char* WIFI_SSID     = "Yadu Phone";
const char* WIFI_PASSWORD = "0000110000";

const char* API_BASE_URL  = "https://hamza.yaduraj.me/v1";
const char* DEVICE_CODE   = "manu";
const char* DEVICE_SECRET = "6109994804";
const char* DEVICE_BLE_NAME = "SecondMind";

const int SAMPLE_RATE    = 16000;
const int CHANNELS       = 1;
const int BITS           = 16;

const bool AUTO_RECORD_DEFAULT = true;
const uint32_t PAIR_MODE_WINDOW_MS = 300000;  // 5 min
const int PAIR_BUTTON_PIN = -1;               // set GPIO if using hardware button
const uint32_t LONG_PRESS_MS = 5000;

// Real command phrases (detected by local DTW template matcher).
const char* WAKE_PHRASE = "hey manu";
const char* STOP_PHRASE = "stop manu";

// Matcher tuning.
const int MATCH_FRAME_MS = 30;
const int MATCH_FEATURE_DIM = 8;
const int MATCH_MAX_TEMPLATE_FRAMES = 96;
const int MATCH_MAX_SEGMENT_FRAMES = 110;
const int MATCH_MIN_SEGMENT_FRAMES = 10;
const float MATCH_SPEECH_START_RMS = 1000.0f;
const float MATCH_SPEECH_STOP_RMS = 550.0f;
const uint32_t MATCH_SEGMENT_END_SILENCE_MS = 500;
const float WAKE_DTW_THRESHOLD = 0.34f;
const float STOP_DTW_THRESHOLD = 0.34f;

// Fallback stop endpointing (RMS range 0..32767).
const float STOP_RMS_THRESHOLD = 500.0f;
const uint32_t STOP_SILENCE_MS = 1200;
const uint32_t LISTEN_LOG_INTERVAL_MS = 3000;

const int MIN_RECORD_SECONDS = 1;
const int MAX_RECORD_SECONDS = 30;

// XIAO ESP32S3 Sense PDM mic pins
#define MIC_CLK  42
#define MIC_DATA 41

// BLE UUIDs (must match app)
static const char* PAIR_SERVICE_UUID = "8b6ad1ca-c85d-4262-b1f6-85e134fdb2f0";
static const char* DEVICE_INFO_CHAR_UUID = "94dcbd89-0f5a-4fb3-9f61-a3d2664d35d1";
static const char* PAIR_NONCE_CHAR_UUID = "2dc45f2c-5924-48cf-a615-f9e3c1070ad4";
static const char* PAIR_TOKEN_CHAR_UUID = "9f8b48ad-e983-4abf-8b56-53f31c0f7596";
static const char* PAIR_STATUS_CHAR_UUID = "ea85f9b1-1c57-4fdd-95ac-5c92b8a07b3d";

const int WAV_HEADER_SIZE = 44;
const int BYTES_PER_SECOND = SAMPLE_RATE * (BITS / 8) * CHANNELS;
const int MATCH_FRAME_BYTES = (BYTES_PER_SECOND * MATCH_FRAME_MS) / 1000;
const int WAV_MAX_DATA_BYTES = BYTES_PER_SECOND * MAX_RECORD_SECONDS;
const int WAV_BUFFER_BYTES = WAV_HEADER_SIZE + WAV_MAX_DATA_BYTES;
const int MAX_MATCH_FRAME_BYTES = 2048;

static i2s_chan_handle_t rx_chan = NULL;
static uint8_t* audioBuf = nullptr;
static String g_deviceJwt;
static size_t g_lastCaptureWavBytes = 0;

struct KeywordTemplate {
  bool ready;
  int frames;
  float feat[MATCH_MAX_TEMPLATE_FRAMES][MATCH_FEATURE_DIM];
};

static KeywordTemplate g_wakeTemplate = {false, 0, {{0}}};
static KeywordTemplate g_stopTemplate = {false, 0, {{0}}};
static bool g_requestEnrollWake = false;
static bool g_requestEnrollStop = false;

// BLE globals
static BLEServer* g_bleServer = nullptr;
static BLEService* g_pairService = nullptr;
static BLECharacteristic* g_deviceInfoChar = nullptr;
static BLECharacteristic* g_pairNonceChar = nullptr;
static BLECharacteristic* g_pairTokenChar = nullptr;
static BLECharacteristic* g_pairStatusChar = nullptr;

// Pairing state
static Preferences g_prefs;
static String g_pairNonce;
static String g_pairTokenFromApp;
static bool g_pairTokenReady = false;
static bool g_isPairingMode = false;
static bool g_isPaired = false;
static bool g_autoRecord = AUTO_RECORD_DEFAULT;
static uint32_t g_pairModeEndAt = 0;
static uint32_t g_buttonPressedAt = 0;
static bool g_buttonWasDown = false;
static uint32_t g_lastNotPairedLogMs = 0;
static volatile bool g_forceWake = false;
static volatile bool g_forceStop = false;

bool runCaptureCycle();
void handleSerialCommands(bool allowImmediateRun = true);
bool authDevice();
bool readMicExact(uint8_t* out, size_t wantedBytes, uint32_t timeoutMs);
bool initWakeWordEngine();
void extractMatchFeature(const uint8_t* frame, size_t bytes, float outFeat[MATCH_FEATURE_DIM]);
float dtwDistance(
    const float a[][MATCH_FEATURE_DIM],
    int aFrames,
    const float b[][MATCH_FEATURE_DIM],
    int bFrames);
bool captureSpeechSegmentFeatures(
    float outFeat[][MATCH_FEATURE_DIM],
    int maxFrames,
    int& outFrames,
    const char* label);
bool enrollTemplate(KeywordTemplate& target, const char* phraseLabel);
bool matchTemplate(
    const float seg[][MATCH_FEATURE_DIM],
    int segFrames,
    const KeywordTemplate& templ,
    float threshold,
    float& outScore);

// ---------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------
String apiUrl(const String& path) {
  return String(API_BASE_URL) + path;
}

String generateNonceHex(size_t bytesLen) {
  static const char* hex = "0123456789abcdef";
  String out;
  out.reserve(bytesLen * 2);
  for (size_t i = 0; i < bytesLen; i++) {
    uint8_t b = static_cast<uint8_t>(esp_random() & 0xFF);
    out += hex[(b >> 4) & 0x0F];
    out += hex[b & 0x0F];
  }
  return out;
}

void setPairStatus(const String& status) {
  if (!g_pairStatusChar) return;
  g_pairStatusChar->setValue(status.c_str());
  g_pairStatusChar->notify();
  Serial.printf("[PAIR] status=%s\n", status.c_str());
}

void updateDeviceInfoChar() {
  if (!g_deviceInfoChar) return;

  StaticJsonDocument<192> doc;
  doc["device_code"] = DEVICE_CODE;
  doc["fw_version"] = "backend-db-v2";

  String payload;
  serializeJson(doc, payload);
  g_deviceInfoChar->setValue(payload.c_str());
}

void startBleAdvertising() {
  BLEAdvertising* adv = BLEDevice::getAdvertising();
  if (!adv) return;
  adv->stop();
  adv->addServiceUUID(PAIR_SERVICE_UUID);
  adv->setScanResponse(true);
  adv->setMinPreferred(0x06);
  adv->setMinPreferred(0x12);
  adv->start();
  Serial.println("[BLE] Advertising started");
}

void stopBleAdvertising() {
  BLEAdvertising* adv = BLEDevice::getAdvertising();
  if (!adv) return;
  adv->stop();
  Serial.println("[BLE] Advertising stopped");
}

// ---------------------------------------------------------------------
// WIFI
// ---------------------------------------------------------------------
bool ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return true;

  Serial.print("[NET] Connecting");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  for (int i = 0; i < 40; i++) {
    delay(500);
    Serial.print('.');
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\n[NET] Connected: " + WiFi.localIP().toString());
      return true;
    }
  }

  Serial.println("\n[NET] Connect failed");
  return false;
}

// ---------------------------------------------------------------------
// WAV HEADER
// ---------------------------------------------------------------------
void writeWAVHeader(uint8_t* buf, int dataBytes) {
  auto w16 = [&](int off, int16_t v) { memcpy(buf + off, &v, 2); };
  auto w32 = [&](int off, int32_t v) { memcpy(buf + off, &v, 4); };

  memcpy(buf, "RIFF", 4);
  w32(4, 36 + dataBytes);
  memcpy(buf + 8, "WAVE", 4);
  memcpy(buf + 12, "fmt ", 4);
  w32(16, 16);
  w16(20, 1);
  w16(22, CHANNELS);
  w32(24, SAMPLE_RATE);
  w32(28, SAMPLE_RATE * CHANNELS * (BITS / 8));
  w16(32, CHANNELS * (BITS / 8));
  w16(34, BITS);
  memcpy(buf + 36, "data", 4);
  w32(40, dataBytes);
}

// ---------------------------------------------------------------------
// MIC INIT
// ---------------------------------------------------------------------
bool initMic() {
  Serial.println("[MIC] Initializing PDM mic...");

  i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_AUTO, I2S_ROLE_MASTER);
  chan_cfg.auto_clear = true;

  esp_err_t err = i2s_new_channel(&chan_cfg, NULL, &rx_chan);
  if (err != ESP_OK) {
    Serial.printf("[MIC] i2s_new_channel failed: %s\n", esp_err_to_name(err));
    return false;
  }

  i2s_pdm_rx_config_t pdm_rx_cfg = {
    .clk_cfg  = I2S_PDM_RX_CLK_DEFAULT_CONFIG(SAMPLE_RATE),
    .slot_cfg = I2S_PDM_RX_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
    .gpio_cfg = {
      .clk  = (gpio_num_t)MIC_CLK,
      .din  = (gpio_num_t)MIC_DATA,
      .invert_flags = { .clk_inv = false },
    },
  };

  err = i2s_channel_init_pdm_rx_mode(rx_chan, &pdm_rx_cfg);
  if (err != ESP_OK) {
    Serial.printf("[MIC] init_pdm_rx_mode failed: %s\n", esp_err_to_name(err));
    i2s_del_channel(rx_chan);
    rx_chan = NULL;
    return false;
  }

  err = i2s_channel_enable(rx_chan);
  if (err != ESP_OK) {
    Serial.printf("[MIC] channel_enable failed: %s\n", esp_err_to_name(err));
    i2s_del_channel(rx_chan);
    rx_chan = NULL;
    return false;
  }

  delay(200);
  Serial.println("[MIC] Ready");
  return true;
}

bool readMicExact(uint8_t* out, size_t wantedBytes, uint32_t timeoutMs) {
  if (!out || wantedBytes == 0) return false;
  size_t total = 0;
  const uint32_t startedAt = millis();

  while (total < wantedBytes) {
    size_t got = 0;
    const esp_err_t err = i2s_channel_read(
        rx_chan,
        out + total,
        static_cast<size_t>(wantedBytes - total),
        &got,
        pdMS_TO_TICKS(timeoutMs));
    if (err != ESP_OK) {
      Serial.printf("[MIC] read error: %s\n", esp_err_to_name(err));
      return false;
    }
    if (got == 0) {
      if (millis() - startedAt > timeoutMs) {
        return false;
      }
      continue;
    }
    total += got;
  }
  return true;
}

bool initWakeWordEngine() {
  if (MATCH_FRAME_BYTES <= 0 || MATCH_FRAME_BYTES > MAX_MATCH_FRAME_BYTES) {
    Serial.printf("[KWS] Invalid match frame bytes: %d\n", MATCH_FRAME_BYTES);
    return false;
  }
  if ((MATCH_FRAME_BYTES % 2) != 0) {
    Serial.println("[KWS] Match frame bytes must align to int16 samples");
    return false;
  }

  g_wakeTemplate.ready = false;
  g_wakeTemplate.frames = 0;
  g_stopTemplate.ready = false;
  g_stopTemplate.frames = 0;

  Serial.printf("[KWS] Local matcher ready frame_ms=%d frame_bytes=%d\n", MATCH_FRAME_MS, MATCH_FRAME_BYTES);
  Serial.println("[KWS] Enroll wake with command '1' and stop with command '2'");
  return true;
}

static float goertzelPower(const int16_t* samples, int n, float targetHz) {
  const float k = floorf(0.5f + (static_cast<float>(n) * targetHz / static_cast<float>(SAMPLE_RATE)));
  const float w = (2.0f * PI * k) / static_cast<float>(n);
  const float coeff = 2.0f * cosf(w);
  float q0 = 0.0f;
  float q1 = 0.0f;
  float q2 = 0.0f;
  for (int i = 0; i < n; i++) {
    q0 = coeff * q1 - q2 + static_cast<float>(samples[i]);
    q2 = q1;
    q1 = q0;
  }
  return q1 * q1 + q2 * q2 - coeff * q1 * q2;
}

void extractMatchFeature(const uint8_t* frame, size_t bytes, float outFeat[MATCH_FEATURE_DIM]) {
  static const float kBandHz[MATCH_FEATURE_DIM] = {350.0f, 550.0f, 800.0f, 1100.0f, 1500.0f, 2000.0f, 2600.0f, 3300.0f};
  const int n = static_cast<int>(bytes / sizeof(int16_t));
  if (!frame || n <= 0) {
    for (int i = 0; i < MATCH_FEATURE_DIM; i++) outFeat[i] = 0.0f;
    return;
  }

  const int16_t* samples = reinterpret_cast<const int16_t*>(frame);
  float sum = 0.0f;
  for (int i = 0; i < MATCH_FEATURE_DIM; i++) {
    const float p = goertzelPower(samples, n, kBandHz[i]);
    const float v = log1pf(max(0.0f, p));
    outFeat[i] = v;
    sum += v;
  }

  if (sum < 1e-6f) {
    for (int i = 0; i < MATCH_FEATURE_DIM; i++) outFeat[i] = 0.0f;
    return;
  }
  for (int i = 0; i < MATCH_FEATURE_DIM; i++) {
    outFeat[i] /= sum;
  }
}

static float frameFeatureDistance(const float a[MATCH_FEATURE_DIM], const float b[MATCH_FEATURE_DIM]) {
  float d = 0.0f;
  for (int i = 0; i < MATCH_FEATURE_DIM; i++) {
    d += fabsf(a[i] - b[i]);
  }
  return d / static_cast<float>(MATCH_FEATURE_DIM);
}

float dtwDistance(
    const float a[][MATCH_FEATURE_DIM],
    int aFrames,
    const float b[][MATCH_FEATURE_DIM],
    int bFrames) {
  if (aFrames <= 0 || bFrames <= 0) return FLT_MAX;
  if (aFrames > MATCH_MAX_SEGMENT_FRAMES || bFrames > MATCH_MAX_TEMPLATE_FRAMES) return FLT_MAX;

  float prev[MATCH_MAX_TEMPLATE_FRAMES + 1];
  float cur[MATCH_MAX_TEMPLATE_FRAMES + 1];
  const float inf = 1e9f;

  for (int j = 0; j <= bFrames; j++) prev[j] = inf;
  prev[0] = 0.0f;

  for (int i = 1; i <= aFrames; i++) {
    cur[0] = inf;
    for (int j = 1; j <= bFrames; j++) {
      const float cost = frameFeatureDistance(a[i - 1], b[j - 1]);
      const float m = min(prev[j], min(cur[j - 1], prev[j - 1]));
      cur[j] = cost + m;
    }
    for (int j = 0; j <= bFrames; j++) prev[j] = cur[j];
  }

  return prev[bFrames] / static_cast<float>(aFrames + bFrames);
}

bool captureSpeechSegmentFeatures(
    float outFeat[][MATCH_FEATURE_DIM],
    int maxFrames,
    int& outFrames,
    const char* label) {
  outFrames = 0;
  bool speechActive = false;
  uint32_t silenceStartedAt = 0;
  uint8_t frameBuf[MAX_MATCH_FRAME_BYTES];
  uint32_t startedAt = millis();

  while (true) {
    handleSerialCommands(false);
    handlePairButton();
    handlePairingState();

    if (!readMicExact(frameBuf, static_cast<size_t>(MATCH_FRAME_BYTES), 1500)) {
      return false;
    }

    const float rms = computeFrameRms(frameBuf, static_cast<size_t>(MATCH_FRAME_BYTES));
    const uint32_t nowMs = millis();

    if (!speechActive) {
      if (rms >= MATCH_SPEECH_START_RMS) {
        speechActive = true;
        silenceStartedAt = 0;
        Serial.printf("[KWS] Speech start for %s\n", label);
      } else {
        if (nowMs - startedAt > 8000) {
          return false;
        }
        continue;
      }
    }

    if (outFrames < maxFrames) {
      extractMatchFeature(frameBuf, static_cast<size_t>(MATCH_FRAME_BYTES), outFeat[outFrames]);
      outFrames++;
    } else {
      break;
    }

    if (rms < MATCH_SPEECH_STOP_RMS) {
      if (silenceStartedAt == 0) silenceStartedAt = nowMs;
      if (nowMs - silenceStartedAt >= MATCH_SEGMENT_END_SILENCE_MS && outFrames >= MATCH_MIN_SEGMENT_FRAMES) {
        break;
      }
    } else {
      silenceStartedAt = 0;
    }
  }

  return outFrames >= MATCH_MIN_SEGMENT_FRAMES;
}

bool enrollTemplate(KeywordTemplate& target, const char* phraseLabel) {
  float segment[MATCH_MAX_SEGMENT_FRAMES][MATCH_FEATURE_DIM];
  int segFrames = 0;
  Serial.printf("[KWS] Say phrase now: \"%s\"\n", phraseLabel);
  if (!captureSpeechSegmentFeatures(segment, MATCH_MAX_SEGMENT_FRAMES, segFrames, phraseLabel)) {
    Serial.printf("[KWS] Enrollment failed for \"%s\"\n", phraseLabel);
    return false;
  }

  const int clipped = min(segFrames, MATCH_MAX_TEMPLATE_FRAMES);
  for (int i = 0; i < clipped; i++) {
    for (int j = 0; j < MATCH_FEATURE_DIM; j++) {
      target.feat[i][j] = segment[i][j];
    }
  }
  target.frames = clipped;
  target.ready = true;
  Serial.printf("[KWS] Enrollment complete for \"%s\" frames=%d\n", phraseLabel, clipped);
  return true;
}

bool matchTemplate(
    const float seg[][MATCH_FEATURE_DIM],
    int segFrames,
    const KeywordTemplate& templ,
    float threshold,
    float& outScore) {
  outScore = FLT_MAX;
  if (!templ.ready || templ.frames <= 0) return false;
  outScore = dtwDistance(seg, segFrames, templ.feat, templ.frames);
  return outScore <= threshold;
}

// ---------------------------------------------------------------------
// WAKE/STOP SESSION CAPTURE (single WAV upload)
// ---------------------------------------------------------------------
float computeFrameRms(const uint8_t* frame, size_t bytes) {
  const size_t sampleCount = bytes / sizeof(int16_t);
  if (sampleCount == 0) return 0.0f;

  const int16_t* samples = reinterpret_cast<const int16_t*>(frame);
  float sum = 0.0f;
  for (size_t i = 0; i < sampleCount; i++) {
    const float s = static_cast<float>(samples[i]);
    sum += s * s;
  }
  return sqrtf(sum / static_cast<float>(sampleCount));
}

bool captureWakeToStopWav(size_t& outWavBytes) {
  if (!rx_chan) {
    Serial.println("[REC] Mic not initialized");
    return false;
  }

  if (!audioBuf) {
    Serial.println("[REC] Audio buffer missing");
    return false;
  }

  if (MATCH_FRAME_BYTES <= 0 || MATCH_FRAME_BYTES > MAX_MATCH_FRAME_BYTES) {
    Serial.println("[REC] Matcher not initialized");
    return false;
  }

  if (!g_wakeTemplate.ready || !g_stopTemplate.ready) {
    Serial.println("[KWS] Templates missing. Enroll with '1' (wake) and '2' (stop).");
    return false;
  }

  uint8_t frameBuf[MAX_MATCH_FRAME_BYTES];
  uint8_t* writePtr = audioBuf + WAV_HEADER_SIZE;
  size_t dataBytes = 0;

  bool recording = g_forceWake;
  uint32_t silenceStartedAt = 0;
  uint32_t lastListenLogAt = 0;
  bool stopSpeechActive = false;
  uint32_t stopSpeechSilenceAt = 0;
  int stopSegFrames = 0;
  float stopSegFeat[MATCH_MAX_SEGMENT_FRAMES][MATCH_FEATURE_DIM];

  if (recording) {
    g_forceWake = false;
    Serial.println("[REC] Wake trigger forced, recording started");
  } else {
    Serial.printf("[REC] Listening for wake phrase \"%s\"...\n", WAKE_PHRASE);
  }

  while (true) {
    handleSerialCommands(false);
    handlePairButton();
    handlePairingState();

    if (!g_isPaired) {
      Serial.println("[REC] Pairing state changed. Capture aborted.");
      return false;
    }

    if (!ensureWiFi()) {
      delay(200);
      continue;
    }

    if (!readMicExact(frameBuf, static_cast<size_t>(MATCH_FRAME_BYTES), 1500)) {
      Serial.println("[REC] Timeout/no mic data");
      return false;
    }

    const float rms = computeFrameRms(frameBuf, static_cast<size_t>(MATCH_FRAME_BYTES));
    const uint32_t nowMs = millis();

    if (!recording) {
      if (nowMs - lastListenLogAt >= LISTEN_LOG_INTERVAL_MS) {
        Serial.printf("[REC] listening rms=%.1f wake=\"%s\"\n", rms, WAKE_PHRASE);
        lastListenLogAt = nowMs;
      }

      if (g_forceWake) {
        g_forceWake = false;
        recording = true;
        silenceStartedAt = 0;
        Serial.println("[REC] Wake trigger forced, recording started");
        continue;
      }

      float wakeSeg[MATCH_MAX_SEGMENT_FRAMES][MATCH_FEATURE_DIM];
      int wakeFrames = 0;
      if (!captureSpeechSegmentFeatures(wakeSeg, MATCH_MAX_SEGMENT_FRAMES, wakeFrames, WAKE_PHRASE)) {
        delay(20);
        continue;
      }
      float wakeScore = FLT_MAX;
      const bool wakeMatch = matchTemplate(wakeSeg, wakeFrames, g_wakeTemplate, WAKE_DTW_THRESHOLD, wakeScore);
      Serial.printf("[KWS] wake score=%.4f threshold=%.4f match=%s\n",
                    wakeScore, WAKE_DTW_THRESHOLD, wakeMatch ? "true" : "false");
      if (!wakeMatch) continue;

      recording = true;
      silenceStartedAt = 0;
      Serial.printf("[REC] Wake phrase detected (\"%s\"), recording started\n", WAKE_PHRASE);
      continue;
    }

    if (dataBytes + static_cast<size_t>(MATCH_FRAME_BYTES) > static_cast<size_t>(WAV_MAX_DATA_BYTES)) {
      Serial.printf("[REC] Max duration reached (%d sec). Stopping.\n", MAX_RECORD_SECONDS);
      break;
    }

    memcpy(writePtr, frameBuf, static_cast<size_t>(MATCH_FRAME_BYTES));
    writePtr += static_cast<size_t>(MATCH_FRAME_BYTES);
    dataBytes += static_cast<size_t>(MATCH_FRAME_BYTES);

    const bool isSilent = (rms < STOP_RMS_THRESHOLD);
    if (g_forceStop) {
      Serial.println("[REC] Stop trigger forced");
      g_forceStop = false;
      break;
    }

    if (!stopSpeechActive) {
      if (rms >= MATCH_SPEECH_START_RMS) {
        stopSpeechActive = true;
        stopSpeechSilenceAt = 0;
        stopSegFrames = 0;
      }
    }
    if (stopSpeechActive) {
      if (stopSegFrames < MATCH_MAX_SEGMENT_FRAMES) {
        extractMatchFeature(frameBuf, static_cast<size_t>(MATCH_FRAME_BYTES), stopSegFeat[stopSegFrames]);
        stopSegFrames++;
      }
      if (rms < MATCH_SPEECH_STOP_RMS) {
        if (stopSpeechSilenceAt == 0) stopSpeechSilenceAt = nowMs;
        if ((nowMs - stopSpeechSilenceAt) >= MATCH_SEGMENT_END_SILENCE_MS &&
            stopSegFrames >= MATCH_MIN_SEGMENT_FRAMES) {
          float stopScore = FLT_MAX;
          const bool stopMatch = matchTemplate(stopSegFeat, stopSegFrames, g_stopTemplate, STOP_DTW_THRESHOLD, stopScore);
          Serial.printf("[KWS] stop score=%.4f threshold=%.4f match=%s\n",
                        stopScore, STOP_DTW_THRESHOLD, stopMatch ? "true" : "false");
          stopSpeechActive = false;
          stopSegFrames = 0;
          if (stopMatch) {
            Serial.printf("[REC] Stop phrase detected (\"%s\")\n", STOP_PHRASE);
            break;
          }
        }
      } else {
        stopSpeechSilenceAt = 0;
      }
    }

    if (isSilent) {
      if (silenceStartedAt == 0) {
        silenceStartedAt = nowMs;
      } else if ((nowMs - silenceStartedAt) >= STOP_SILENCE_MS) {
        Serial.printf("[REC] Stop silence reached (%lu ms)\n", static_cast<unsigned long>(nowMs - silenceStartedAt));
        break;
      }
    } else {
      silenceStartedAt = 0;
    }
  }

  if (dataBytes < static_cast<size_t>(MIN_RECORD_SECONDS * BYTES_PER_SECOND)) {
    Serial.println("[REC] Captured audio too short, skipping upload");
    return false;
  }

  writeWAVHeader(audioBuf, static_cast<int>(dataBytes));
  outWavBytes = WAV_HEADER_SIZE + dataBytes;

  const float durationSec = static_cast<float>(dataBytes) / static_cast<float>(BYTES_PER_SECOND);
  Serial.printf("[REC] Completed session %.2f sec, wav_bytes=%u\n", durationSec, static_cast<unsigned>(outWavBytes));
  return true;
}

// ---------------------------------------------------------------------
// DEVICE AUTH
// ---------------------------------------------------------------------
bool authDevice() {
  if (!ensureWiFi()) return false;

  StaticJsonDocument<256> req;
  req["device_code"] = DEVICE_CODE;
  req["secret"] = DEVICE_SECRET;

  String payload;
  serializeJson(req, payload);

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  String url = apiUrl("/device/auth");
  http.begin(client, url);
  http.setTimeout(15000);
  http.addHeader("Content-Type", "application/json");

  int code = http.POST(payload);
  String resp = http.getString();
  http.end();

  Serial.printf("[AUTH] HTTP %d\n", code);
  if (code != 200) {
    Serial.printf("[AUTH] Failed: %s\n", resp.c_str());
    return false;
  }

  StaticJsonDocument<1024> doc;
  if (deserializeJson(doc, resp)) {
    Serial.println("[AUTH] JSON parse error");
    return false;
  }

  g_deviceJwt = String((const char*)doc["access_token"]);
  if (g_deviceJwt.isEmpty()) {
    Serial.println("[AUTH] access_token missing");
    return false;
  }

  Serial.println("[AUTH] Device token OK");
  return true;
}

// ---------------------------------------------------------------------
// PAIRING COMPLETE CALL
// ---------------------------------------------------------------------
bool completePairingWithBackend(const String& pairToken) {
  if (pairToken.isEmpty()) return false;
  if (!ensureWiFi()) return false;
  if (g_deviceJwt.isEmpty() && !authDevice()) return false;

  auto doComplete = [&](const String& token, String& respOut, int& codeOut) -> bool {
    StaticJsonDocument<256> req;
    req["pair_token"] = pairToken;

    String payload;
    serializeJson(req, payload);

    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;
    String url = apiUrl("/device/pairing/complete");
    if (!http.begin(client, url)) {
      Serial.println("[PAIR] http.begin failed");
      return false;
    }

    http.setTimeout(20000);
    http.addHeader("Authorization", "Bearer " + token);
    http.addHeader("Content-Type", "application/json");

    codeOut = http.POST(payload);
    respOut = http.getString();
    http.end();
    return true;
  };

  int code = 0;
  String resp;
  if (!doComplete(g_deviceJwt, resp, code)) return false;

  if (code == 401) {
    Serial.println("[PAIR] Token expired, re-auth");
    if (!authDevice()) return false;
    if (!doComplete(g_deviceJwt, resp, code)) return false;
  }

  Serial.printf("[PAIR] complete HTTP %d\n", code);
  if (code != 200) {
    Serial.printf("[PAIR] complete failed: %s\n", resp.c_str());
    return false;
  }

  g_isPaired = true;
  g_prefs.putBool("paired", true);
  Serial.println("[PAIR] Device paired successfully");
  return true;
}

// ---------------------------------------------------------------------
// UPLOAD WAV TO BACKEND (DB STORAGE)
// ---------------------------------------------------------------------
bool uploadToBackend(String& outSessionId) {
  if (!ensureWiFi()) return false;
  if (g_deviceJwt.isEmpty() && !authDevice()) return false;

  auto doUpload = [&](const String& token, String& respOut, int& codeOut) -> bool {
    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;
    String url = apiUrl("/device/captures/upload-wav");
    if (!http.begin(client, url)) {
      Serial.println("[UPLOAD] http.begin failed");
      return false;
    }

    http.setTimeout(60000);
    http.addHeader("Authorization", "Bearer " + token);
    http.addHeader("Content-Type", "audio/wav");
    http.addHeader("X-Sample-Rate", String(SAMPLE_RATE));
    http.addHeader("X-Channels", String(CHANNELS));
    http.addHeader("X-Codec", "pcm16le");

    if (g_lastCaptureWavBytes == 0) {
      Serial.println("[UPLOAD] No captured WAV bytes available");
      http.end();
      return false;
    }

    codeOut = http.POST(audioBuf, static_cast<int>(g_lastCaptureWavBytes));
    respOut = http.getString();
    http.end();
    return true;
  };

  int code = 0;
  String resp;
  if (!doUpload(g_deviceJwt, resp, code)) return false;

  if (code == 401) {
    Serial.println("[UPLOAD] Token expired, re-auth");
    if (!authDevice()) return false;
    if (!doUpload(g_deviceJwt, resp, code)) return false;
  }

  Serial.printf("[UPLOAD] HTTP %d\n", code);
  if (code != 201) {
    Serial.printf("[UPLOAD] Failed: %s\n", resp.c_str());
    return false;
  }

  StaticJsonDocument<1024> doc;
  if (deserializeJson(doc, resp)) {
    Serial.println("[UPLOAD] JSON parse error");
    return false;
  }

  outSessionId = String((const char*)doc["session_id"]);
  String status = String((const char*)doc["status"]);
  Serial.printf("[UPLOAD] OK session_id=%s status=%s\n", outSessionId.c_str(), status.c_str());
  return !outSessionId.isEmpty();
}

// ---------------------------------------------------------------------
// BLE CALLBACKS
// ---------------------------------------------------------------------
class PairTokenCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* characteristic) override {
    if (!characteristic) return;

    String value = characteristic->getValue();
    value.trim();
    if (value.isEmpty()) return;

    if (!g_isPairingMode) {
      Serial.println("[PAIR] Ignoring token write (not in pairing mode)");
      setPairStatus("idle");
      return;
    }

    g_pairTokenFromApp = value;
    g_pairTokenReady = true;
    setPairStatus("token_received");
  }
};

// ---------------------------------------------------------------------
// BLE SETUP
// ---------------------------------------------------------------------
void setupBle() {
  BLEDevice::init(DEVICE_BLE_NAME);
  g_bleServer = BLEDevice::createServer();
  g_pairService = g_bleServer->createService(PAIR_SERVICE_UUID);

  g_deviceInfoChar = g_pairService->createCharacteristic(
      DEVICE_INFO_CHAR_UUID,
      BLECharacteristic::PROPERTY_READ);

  g_pairNonceChar = g_pairService->createCharacteristic(
      PAIR_NONCE_CHAR_UUID,
      BLECharacteristic::PROPERTY_READ);

  g_pairTokenChar = g_pairService->createCharacteristic(
      PAIR_TOKEN_CHAR_UUID,
      BLECharacteristic::PROPERTY_WRITE);
  g_pairTokenChar->setCallbacks(new PairTokenCallbacks());

  g_pairStatusChar = g_pairService->createCharacteristic(
      PAIR_STATUS_CHAR_UUID,
      BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ);
  g_pairStatusChar->addDescriptor(new BLE2902());

  updateDeviceInfoChar();
  g_pairNonceChar->setValue("not_in_pair_mode");
  g_pairStatusChar->setValue("idle");

  g_pairService->start();
  startBleAdvertising();
}

// ---------------------------------------------------------------------
// PAIRING STATE HANDLERS
// ---------------------------------------------------------------------
void enterPairingMode() {
  g_isPairingMode = true;
  g_pairTokenReady = false;
  g_pairTokenFromApp = "";
  g_pairNonce = generateNonceHex(16);
  g_pairModeEndAt = millis() + PAIR_MODE_WINDOW_MS;

  if (g_pairNonceChar) g_pairNonceChar->setValue(g_pairNonce.c_str());

  Serial.printf("[PAIR] Entered pairing mode nonce=%s\n", g_pairNonce.c_str());
  setPairStatus("pairing_mode");
  startBleAdvertising();
}

void exitPairingMode(const String& finalStatus) {
  g_isPairingMode = false;
  g_pairTokenReady = false;
  g_pairTokenFromApp = "";
  g_pairNonce = "";

  if (g_pairNonceChar) g_pairNonceChar->setValue("not_in_pair_mode");
  setPairStatus(finalStatus);

  if (finalStatus == "success") {
    g_isPaired = true;
    g_prefs.putBool("paired", true);
    delay(200);
    setPairStatus("idle");
  }
}

void handlePairButton() {
#if PAIR_BUTTON_PIN < 0
  return;
#else
  bool down = digitalRead(PAIR_BUTTON_PIN) == LOW;
  if (down && !g_buttonWasDown) g_buttonPressedAt = millis();
  if (!down && g_buttonWasDown) g_buttonPressedAt = 0;
  g_buttonWasDown = down;

  if (down && g_buttonPressedAt > 0 && (millis() - g_buttonPressedAt) >= LONG_PRESS_MS && !g_isPairingMode) {
    enterPairingMode();
    g_buttonPressedAt = 0;
  }
#endif
}

void handlePairingState() {
  if (!g_isPairingMode) return;

  if (millis() > g_pairModeEndAt) {
    Serial.println("[PAIR] Pairing window expired");
    exitPairingMode("expired");
    return;
  }

  if (!g_pairTokenReady) return;

  g_pairTokenReady = false;
  setPairStatus("validating");

  if (completePairingWithBackend(g_pairTokenFromApp)) {
    exitPairingMode("success");
  } else {
    setPairStatus("failed");
    // Stay in pairing mode to allow retry until window expiry.
  }
}

// ---------------------------------------------------------------------
// SERIAL COMMANDS
// ---------------------------------------------------------------------
void printSerialHelp() {
  Serial.println("\n=== ESP32 BackendDB Commands ===");
  Serial.printf("Wake phrase: \"%s\"\n", WAKE_PHRASE);
  Serial.printf("Stop phrase: \"%s\"\n", STOP_PHRASE);
  Serial.println("1   : enroll wake phrase template");
  Serial.println("2   : enroll stop phrase template");
  Serial.println("p/P : enter pairing mode");
  Serial.println("x   : clear paired flag + enter pairing mode");
  Serial.println("u   : re-auth device token");
  Serial.println("a   : toggle auto capture loop on/off");
  Serial.println("w   : force wake trigger (start capture)");
  Serial.println("s   : force stop trigger (end capture)");
  Serial.println("r   : run one immediate wake->stop capture+upload");
  Serial.println("h   : show this help");
  Serial.println("================================\n");
}

bool runCaptureCycle() {
  Serial.println("══════════════════════════════");
  Serial.printf("[MEM] free_heap=%d\n", ESP.getFreeHeap());

  if (!ensureWiFi()) {
    delay(5000);
    return false;
  }

  size_t wavBytes = 0;
  if (!captureWakeToStopWav(wavBytes)) {
    delay(3000);
    return false;
  }
  g_lastCaptureWavBytes = wavBytes;

  String sessionId;
  if (!uploadToBackend(sessionId)) {
    delay(3000);
    return false;
  }

  Serial.printf("[DONE] Uploaded capture session=%s\n\n", sessionId.c_str());
  return true;
}

void processSerialCommand(char cmd, bool allowImmediateRun) {
  switch (cmd) {
    case '1':
      g_requestEnrollWake = true;
      Serial.printf("[KWS] Wake enrollment requested for \"%s\"\n", WAKE_PHRASE);
      break;
    case '2':
      g_requestEnrollStop = true;
      Serial.printf("[KWS] Stop enrollment requested for \"%s\"\n", STOP_PHRASE);
      break;
    case 'p':
      enterPairingMode();
      break;
    case 'x':
      g_isPaired = false;
      g_prefs.putBool("paired", false);
      Serial.println("[PAIR] paired flag cleared");
      enterPairingMode();
      break;
    case 'u':
      authDevice();
      break;
    case 'a':
      g_autoRecord = !g_autoRecord;
      Serial.printf("[REC] Auto capture %s\n", g_autoRecord ? "ON" : "OFF");
      break;
    case 'w':
      g_forceWake = true;
      Serial.println("[REC] Force wake trigger queued");
      break;
    case 's':
      g_forceStop = true;
      Serial.println("[REC] Force stop trigger queued");
      break;
    case 'r':
      if (!allowImmediateRun) {
        Serial.println("[REC] Ignored 'r' while capture loop is active");
      } else if (!g_isPaired) {
        Serial.println("[REC] Device not paired. Pair first with 'p'.");
      } else {
        runCaptureCycle();
      }
      break;
    case 'h':
      printSerialHelp();
      break;
    default:
      break;
  }
}

void handleSerialCommands(bool allowImmediateRun) {
  while (Serial.available()) {
    char c = static_cast<char>(Serial.read());
    char cmd = static_cast<char>(tolower(static_cast<unsigned char>(c)));
    processSerialCommand(cmd, allowImmediateRun);
  }
}

// ---------------------------------------------------------------------
// SETUP
// ---------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== ESP32-S3 Backend DB Audio Upload + Pairing ===");

#if PAIR_BUTTON_PIN >= 0
  pinMode(PAIR_BUTTON_PIN, INPUT_PULLUP);
#endif

  g_prefs.begin("secondmind", false);
  g_isPaired = g_prefs.getBool("paired", false);
  g_autoRecord = AUTO_RECORD_DEFAULT;

  audioBuf = (uint8_t*)ps_malloc(WAV_BUFFER_BYTES);
  if (!audioBuf) {
    Serial.println("FATAL: ps_malloc failed. Set Tools -> PSRAM -> OPI PSRAM.");
    while (true) delay(1000);
  }
  Serial.printf("[MEM] wav_buf_max=%d free_heap=%d\n", WAV_BUFFER_BYTES, ESP.getFreeHeap());

  if (!ensureWiFi()) {
    Serial.println("[NET] Initial WiFi connect failed. Will retry in loop.");
  }

  if (!initMic()) {
    Serial.println("[MIC] FATAL: mic init failed");
    while (true) delay(1000);
  }

  if (!initWakeWordEngine()) {
    Serial.println("[KWS] FATAL: wake-word engine init failed");
    while (true) delay(1000);
  }
  Serial.println("[KWS] Run '1' then speak wake phrase, run '2' then speak stop phrase.");

  if (!authDevice()) {
    Serial.println("[AUTH] Initial auth failed. Will retry in loop.");
  }

  setupBle();

  if (g_isPaired) {
    Serial.println("[PAIR] Device already paired.");
    setPairStatus("idle");
  } else {
    Serial.println("[PAIR] Device not paired. Send 'p' in Serial Monitor.");
  }

  printSerialHelp();
  Serial.println("[READY] Recorder started");
}

// ---------------------------------------------------------------------
// LOOP
// ---------------------------------------------------------------------
void loop() {
  handleSerialCommands(true);
  handlePairButton();
  handlePairingState();

  if (g_requestEnrollWake) {
    g_requestEnrollWake = false;
    enrollTemplate(g_wakeTemplate, WAKE_PHRASE);
  }
  if (g_requestEnrollStop) {
    g_requestEnrollStop = false;
    enrollTemplate(g_stopTemplate, STOP_PHRASE);
  }

  if (!g_isPaired) {
    if (millis() - g_lastNotPairedLogMs > 5000) {
      Serial.println("[PAIR] Waiting for pairing. Send 'p' to enter pairing mode.");
      g_lastNotPairedLogMs = millis();
    }
    delay(20);
    return;
  }

  if (!g_autoRecord) {
    delay(20);
    return;
  }

  runCaptureCycle();
  delay(2000);
}
