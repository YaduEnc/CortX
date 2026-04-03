/*
 * =====================================================================
 *  ESP32-S3 Sense — Continuous Chunk Upload + BLE Pairing
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
 *    5) Device starts a capture session (/v1/device/capture/sessions)
 *    6) Device records and uploads continuous PCM chunks:
 *       chunk B1 upload while chunk B2 records (ping-pong buffers)
 *    7) Device finalizes session (/v1/device/capture/sessions/{id}/finalize)
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
#include <string.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>

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
const int TARGET_CHUNK_SECONDS = 10;

const int BACKEND_MAX_CHUNK_BYTES = 256000;
const int PCM_BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * (BITS / 8);
const int CHUNK_BYTES = (TARGET_CHUNK_SECONDS * PCM_BYTES_PER_SECOND <= BACKEND_MAX_CHUNK_BYTES)
                        ? (TARGET_CHUNK_SECONDS * PCM_BYTES_PER_SECOND)
                        : BACKEND_MAX_CHUNK_BYTES;
const int CHUNK_SECONDS = CHUNK_BYTES / PCM_BYTES_PER_SECOND;
const uint32_t CHUNK_MS = static_cast<uint32_t>((static_cast<uint64_t>(CHUNK_BYTES) * 1000ULL) / PCM_BYTES_PER_SECOND);

const bool AUTO_STREAM_DEFAULT = true;
const bool AUTO_ROLLING_FINALIZE = true;
const uint32_t AUTO_FINALIZE_AFTER_CHUNKS = 2;  // auto-send one file every ~16s with current chunk size
const uint32_t PAIR_MODE_WINDOW_MS = 300000;  // 5 min
const int PAIR_BUTTON_PIN = -1;               // set GPIO if using hardware button
const uint32_t LONG_PRESS_MS = 5000;

// XIAO ESP32S3 Sense PDM mic pins
#define MIC_CLK  42
#define MIC_DATA 41

// BLE UUIDs (must match app)
static const char* PAIR_SERVICE_UUID = "8b6ad1ca-c85d-4262-b1f6-85e134fdb2f0";
static const char* DEVICE_INFO_CHAR_UUID = "94dcbd89-0f5a-4fb3-9f61-a3d2664d35d1";
static const char* PAIR_NONCE_CHAR_UUID = "2dc45f2c-5924-48cf-a615-f9e3c1070ad4";
static const char* PAIR_TOKEN_CHAR_UUID = "9f8b48ad-e983-4abf-8b56-53f31c0f7596";
static const char* PAIR_STATUS_CHAR_UUID = "ea85f9b1-1c57-4fdd-95ac-5c92b8a07b3d";

struct ChunkUploadJob {
  char sessionId[37];
  uint32_t chunkIndex;
  uint32_t startMs;
  uint32_t endMs;
  uint32_t byteSize;
  uint8_t* buffer;
};

static i2s_chan_handle_t rx_chan = NULL;
static String g_deviceJwt;

// Chunk streaming globals
static uint8_t* g_chunkBufA = nullptr;
static uint8_t* g_chunkBufB = nullptr;
static SemaphoreHandle_t g_bufASem = nullptr;
static SemaphoreHandle_t g_bufBSem = nullptr;
static QueueHandle_t g_uploadQueue = nullptr;
static TaskHandle_t g_uploaderTaskHandle = nullptr;

static String g_activeSessionId;
static uint32_t g_nextChunkIndex = 0;
static bool g_useBufferA = true;
static bool g_autoStream = AUTO_STREAM_DEFAULT;
static volatile bool g_streamFault = false;
static volatile bool g_finalizeRequested = false;
static volatile bool g_nonRetryableChunkFailure = false;
static String g_finalizeReason = "device_stop";
static uint32_t g_lastWifiBeginMs = 0;

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
static uint32_t g_pairModeEndAt = 0;
static uint32_t g_buttonPressedAt = 0;
static bool g_buttonWasDown = false;
static uint32_t g_lastNotPairedLogMs = 0;

bool authDevice();
bool runContinuousChunkOnce();
void handleSerialCommands(bool allowImmediateRun = true);
void requestFinalize(const char* reason);

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

void requestFinalize(const char* reason) {
  if (reason && reason[0] != '\0') {
    g_finalizeReason = String(reason);
  } else {
    g_finalizeReason = "device_stop";
  }
  g_finalizeRequested = true;
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
  doc["fw_version"] = "chunk-stream-v1";

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

// ---------------------------------------------------------------------
// WIFI
// ---------------------------------------------------------------------
bool ensureWiFi() {
  wl_status_t st = WiFi.status();
  if (st == WL_CONNECTED) return true;

  if (st == WL_IDLE_STATUS) {
    // A connection attempt is already in progress; do not call begin() again.
    for (int i = 0; i < 8; i++) {
      delay(250);
      if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n[NET] Connected: " + WiFi.localIP().toString());
        return true;
      }
    }
    return false;
  }

  const uint32_t now = millis();
  if (g_lastWifiBeginMs != 0 && (now - g_lastWifiBeginMs) < 10000) {
    return false;
  }
  g_lastWifiBeginMs = now;

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
// MIC INIT / RECORD
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

bool recordPcmChunk(uint8_t* dst, size_t wantBytes) {
  if (!rx_chan || !dst || wantBytes == 0) return false;
  size_t total = 0;

  while (total < wantBytes) {
    handleSerialCommands(false);

    if (g_finalizeRequested) {
      Serial.println("[REC] Stop requested; discarding in-progress chunk");
      return false;
    }

    if (!g_isPaired) {
      Serial.println("[REC] Pairing changed; abort chunk");
      return false;
    }

    const size_t toRead = min(static_cast<size_t>(1024), wantBytes - total);
    size_t got = 0;
    esp_err_t err = i2s_channel_read(rx_chan, dst + total, toRead, &got, pdMS_TO_TICKS(2000));
    if (err != ESP_OK) {
      Serial.printf("[REC] read error: %s\n", esp_err_to_name(err));
      return false;
    }
    if (got == 0) {
      Serial.println("[REC] Timeout/no mic data");
      return false;
    }
    total += got;
  }

  return true;
}

// ---------------------------------------------------------------------
// AUTH
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
  if (!http.begin(client, url)) {
    Serial.println("[AUTH] http.begin failed");
    return false;
  }
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
// CAPTURE SESSION API
// ---------------------------------------------------------------------
bool startCaptureSession(String& outSessionId) {
  if (!ensureWiFi()) return false;
  if (g_deviceJwt.isEmpty() && !authDevice()) return false;

  auto doStart = [&](const String& token, String& respOut, int& codeOut) -> bool {
    StaticJsonDocument<192> req;
    req["sample_rate"] = SAMPLE_RATE;
    req["channels"] = CHANNELS;
    req["codec"] = "pcm16le";

    String payload;
    serializeJson(req, payload);

    WiFiClientSecure client;
    client.setInsecure();
    HTTPClient http;
    String url = apiUrl("/device/capture/sessions");
    if (!http.begin(client, url)) {
      Serial.println("[SESSION] http.begin failed");
      return false;
    }

    http.setTimeout(15000);
    http.addHeader("Authorization", "Bearer " + token);
    http.addHeader("Content-Type", "application/json");

    codeOut = http.POST(payload);
    respOut = http.getString();
    http.end();
    return true;
  };

  int code = 0;
  String resp;
  if (!doStart(g_deviceJwt, resp, code)) return false;
  if (code == 401) {
    if (!authDevice()) return false;
    if (!doStart(g_deviceJwt, resp, code)) return false;
  }

  Serial.printf("[SESSION] start HTTP %d\n", code);
  if (code != 201) {
    Serial.printf("[SESSION] start failed: %s\n", resp.c_str());
    return false;
  }

  StaticJsonDocument<1024> doc;
  if (deserializeJson(doc, resp)) {
    Serial.println("[SESSION] start JSON parse error");
    return false;
  }

  outSessionId = String((const char*)doc["session_id"]);
  if (outSessionId.isEmpty()) {
    Serial.println("[SESSION] start missing session_id");
    return false;
  }

  Serial.printf("[SESSION] started id=%s\n", outSessionId.c_str());
  return true;
}

bool uploadCaptureChunkHttp(const ChunkUploadJob& job) {
  if (!ensureWiFi()) return false;
  if (g_deviceJwt.isEmpty() && !authDevice()) return false;

  auto doUpload = [&](const String& token, String& respOut, int& codeOut) -> bool {
    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;
    String url = apiUrl("/device/capture/chunks");
    if (!http.begin(client, url)) {
      Serial.println("[CHUNK] http.begin failed");
      return false;
    }

    http.setTimeout(30000);
    http.addHeader("Authorization", "Bearer " + token);
    http.addHeader("Content-Type", "application/octet-stream");
    http.addHeader("X-Session-Id", String(job.sessionId));
    http.addHeader("X-Chunk-Index", String(job.chunkIndex));
    http.addHeader("X-Start-Ms", String(job.startMs));
    http.addHeader("X-End-Ms", String(job.endMs));
    http.addHeader("X-Sample-Rate", String(SAMPLE_RATE));
    http.addHeader("X-Channels", String(CHANNELS));
    http.addHeader("X-Codec", "pcm16le");

    codeOut = http.POST(job.buffer, static_cast<int>(job.byteSize));
    respOut = http.getString();
    http.end();
    return true;
  };

  int code = 0;
  String resp;
  if (!doUpload(g_deviceJwt, resp, code)) return false;
  if (code == 401) {
    if (!authDevice()) return false;
    if (!doUpload(g_deviceJwt, resp, code)) return false;
  }

  if (code == 413) {
    Serial.printf("[CHUNK] payload too large idx=%lu bytes=%lu (server max too low): %s\n",
                  static_cast<unsigned long>(job.chunkIndex),
                  static_cast<unsigned long>(job.byteSize),
                  resp.c_str());
    g_nonRetryableChunkFailure = true;
    return false;
  }

  if (code != 201 && code != 200) {
    Serial.printf("[CHUNK] upload failed idx=%lu HTTP %d: %s\n",
                  static_cast<unsigned long>(job.chunkIndex),
                  code,
                  resp.c_str());
    return false;
  }

  Serial.printf("[CHUNK] stored idx=%lu bytes=%lu\n",
                static_cast<unsigned long>(job.chunkIndex),
                static_cast<unsigned long>(job.byteSize));
  return true;
}

bool finalizeCaptureSessionHttp(const String& sessionId, const String& reason) {
  if (sessionId.isEmpty()) return true;
  if (!ensureWiFi()) return false;
  if (g_deviceJwt.isEmpty() && !authDevice()) return false;

  auto doFinalize = [&](const String& token, String& respOut, int& codeOut) -> bool {
    StaticJsonDocument<192> req;
    req["reason"] = reason;
    String payload;
    serializeJson(req, payload);

    WiFiClientSecure client;
    client.setInsecure();
    HTTPClient http;
    String url = apiUrl("/device/capture/sessions/" + sessionId + "/finalize");
    if (!http.begin(client, url)) {
      Serial.println("[SESSION] finalize http.begin failed");
      return false;
    }

    http.setTimeout(30000);
    http.addHeader("Authorization", "Bearer " + token);
    http.addHeader("Content-Type", "application/json");

    codeOut = http.POST(payload);
    respOut = http.getString();
    http.end();
    return true;
  };

  int code = 0;
  String resp;
  if (!doFinalize(g_deviceJwt, resp, code)) return false;
  if (code == 401) {
    if (!authDevice()) return false;
    if (!doFinalize(g_deviceJwt, resp, code)) return false;
  }

  Serial.printf("[SESSION] finalize HTTP %d\n", code);
  if (code != 200) {
    Serial.printf("[SESSION] finalize failed: %s\n", resp.c_str());
    return false;
  }

  Serial.printf("[SESSION] finalized id=%s\n", sessionId.c_str());
  return true;
}

// ---------------------------------------------------------------------
// UPLOAD WORKER (parallel uploader task)
// ---------------------------------------------------------------------
void releaseBufferSemaphore(uint8_t* buf) {
  if (buf == g_chunkBufA && g_bufASem) {
    xSemaphoreGive(g_bufASem);
  } else if (buf == g_chunkBufB && g_bufBSem) {
    xSemaphoreGive(g_bufBSem);
  }
}

void uploaderTask(void* param) {
  (void)param;
  ChunkUploadJob job;
  for (;;) {
    if (xQueueReceive(g_uploadQueue, &job, portMAX_DELAY) == pdTRUE) {
      bool ok = false;
      g_nonRetryableChunkFailure = false;
      for (int attempt = 0; attempt < 3; attempt++) {
        if (uploadCaptureChunkHttp(job)) {
          ok = true;
          break;
        }
        if (g_nonRetryableChunkFailure) break;
        delay(500 + attempt * 500);
      }
      if (!ok) {
        Serial.printf("[CHUNK] FATAL upload failed idx=%lu\n", static_cast<unsigned long>(job.chunkIndex));
        g_streamFault = true;
      }
      releaseBufferSemaphore(job.buffer);
    }
  }
}

bool waitForPendingUploads(uint32_t timeoutMs) {
  const uint32_t start = millis();
  while ((millis() - start) < timeoutMs) {
    const bool queueEmpty = (uxQueueMessagesWaiting(g_uploadQueue) == 0);

    bool aFree = false;
    bool bFree = false;
    if (g_bufASem) {
      if (xSemaphoreTake(g_bufASem, 0) == pdTRUE) {
        aFree = true;
        xSemaphoreGive(g_bufASem);
      }
    }
    if (g_bufBSem) {
      if (xSemaphoreTake(g_bufBSem, 0) == pdTRUE) {
        bFree = true;
        xSemaphoreGive(g_bufBSem);
      }
    }

    if (queueEmpty && aFree && bFree) return true;
    delay(25);
  }
  return false;
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
// BLE CALLBACKS
// ---------------------------------------------------------------------
class PairTokenCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* characteristic) override {
    if (!characteristic) return;

    String value = characteristic->getValue();
    value.trim();
    if (value.isEmpty()) return;

    if (!g_isPairingMode) {
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
  }
}

// ---------------------------------------------------------------------
// STREAM CONTROL
// ---------------------------------------------------------------------
bool ensureSessionStarted() {
  if (!g_activeSessionId.isEmpty()) return true;

  String sid;
  if (!startCaptureSession(sid)) return false;
  g_activeSessionId = sid;
  g_nextChunkIndex = 0;
  g_useBufferA = true;
  return true;
}

bool stopAndFinalizeSession(const String& reason) {
  if (g_activeSessionId.isEmpty()) return true;

  Serial.println("[SESSION] Waiting pending chunk uploads...");
  if (!waitForPendingUploads(120000)) {
    Serial.println("[SESSION] Timeout waiting pending uploads");
    return false;
  }

  if (!finalizeCaptureSessionHttp(g_activeSessionId, reason)) {
    return false;
  }

  g_activeSessionId = "";
  g_nextChunkIndex = 0;
  g_useBufferA = true;
  return true;
}

bool runContinuousChunkOnce() {
  SemaphoreHandle_t sem = g_useBufferA ? g_bufASem : g_bufBSem;
  uint8_t* buf = g_useBufferA ? g_chunkBufA : g_chunkBufB;

  if (xSemaphoreTake(sem, pdMS_TO_TICKS(10000)) != pdTRUE) {
    Serial.println("[REC] Timeout waiting free chunk buffer");
    return false;
  }

  const uint32_t idx = g_nextChunkIndex;
  const uint32_t startMs = idx * CHUNK_MS;
  const uint32_t endMs = startMs + CHUNK_MS;

  Serial.printf("[REC] Recording chunk idx=%lu (%d sec)\n", static_cast<unsigned long>(idx), CHUNK_SECONDS);
  if (!recordPcmChunk(buf, static_cast<size_t>(CHUNK_BYTES))) {
    xSemaphoreGive(sem);
    return false;
  }

  // Start backend capture session only when first chunk is actually ready,
  // so aborted first-chunk attempts do not leave empty sessions server-side.
  if (g_activeSessionId.isEmpty()) {
    String sid;
    if (!startCaptureSession(sid)) {
      xSemaphoreGive(sem);
      return false;
    }
    g_activeSessionId = sid;
    g_nextChunkIndex = 0;
  }

  ChunkUploadJob job;
  memset(&job, 0, sizeof(job));
  strncpy(job.sessionId, g_activeSessionId.c_str(), sizeof(job.sessionId) - 1);
  job.chunkIndex = idx;
  job.startMs = startMs;
  job.endMs = endMs;
  job.byteSize = static_cast<uint32_t>(CHUNK_BYTES);
  job.buffer = buf;

  if (xQueueSend(g_uploadQueue, &job, pdMS_TO_TICKS(5000)) != pdTRUE) {
    Serial.println("[REC] Failed to queue chunk upload");
    xSemaphoreGive(sem);
    return false;
  }

  g_nextChunkIndex++;
  g_useBufferA = !g_useBufferA;
  Serial.printf("[REC] Queued upload idx=%lu\n", static_cast<unsigned long>(idx));

  if (AUTO_ROLLING_FINALIZE && g_nextChunkIndex >= AUTO_FINALIZE_AFTER_CHUNKS) {
    Serial.printf("[SESSION] Auto finalize requested after %lu chunks\n",
                  static_cast<unsigned long>(g_nextChunkIndex));
    requestFinalize("auto_roll");
  }

  return true;
}

// ---------------------------------------------------------------------
// SERIAL COMMANDS
// ---------------------------------------------------------------------
void printSerialHelp() {
  Serial.println("\n=== ESP32 BackendDB Commands ===");
  if (AUTO_ROLLING_FINALIZE) {
    Serial.printf("auto: finalize every %lu chunks (~%lu sec)\n",
                  static_cast<unsigned long>(AUTO_FINALIZE_AFTER_CHUNKS),
                  static_cast<unsigned long>((AUTO_FINALIZE_AFTER_CHUNKS * CHUNK_MS) / 1000));
  }
  Serial.println("p/P : enter pairing mode");
  Serial.println("x   : clear paired flag + enter pairing mode");
  Serial.println("u   : re-auth device token");
  Serial.println("a   : toggle continuous chunk stream on/off");
  Serial.println("s   : stop stream + finalize active session");
  Serial.println("r   : record and queue one chunk now");
  Serial.println("h   : show this help");
  Serial.println("================================\n");
}

void processSerialCommand(char cmd, bool allowImmediateRun) {
  switch (cmd) {
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
      g_autoStream = !g_autoStream;
      Serial.printf("[REC] Continuous chunk stream %s\n", g_autoStream ? "ON" : "OFF");
      if (!g_autoStream) requestFinalize("device_stop");
      break;
    case 's':
      g_autoStream = false;
      requestFinalize("device_stop");
      Serial.println("[REC] Stop requested; will finalize session");
      break;
    case 'r':
      if (!allowImmediateRun) {
        Serial.println("[REC] Ignored 'r' while chunk loop is active");
      } else if (!g_isPaired) {
        Serial.println("[REC] Device not paired. Pair first with 'p'.");
      } else {
        runContinuousChunkOnce();
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
  Serial.println("\n=== ESP32-S3 Continuous Chunk Upload + Pairing ===");

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);

#if PAIR_BUTTON_PIN >= 0
  pinMode(PAIR_BUTTON_PIN, INPUT_PULLUP);
#endif

  g_prefs.begin("secondmind", false);
  g_isPaired = g_prefs.getBool("paired", false);
  g_autoStream = AUTO_STREAM_DEFAULT;

  g_chunkBufA = static_cast<uint8_t*>(ps_malloc(CHUNK_BYTES));
  g_chunkBufB = static_cast<uint8_t*>(ps_malloc(CHUNK_BYTES));
  if (!g_chunkBufA || !g_chunkBufB) {
    Serial.println("FATAL: chunk buffer ps_malloc failed. Set Tools -> PSRAM -> OPI PSRAM.");
    while (true) delay(1000);
  }

  g_bufASem = xSemaphoreCreateBinary();
  g_bufBSem = xSemaphoreCreateBinary();
  g_uploadQueue = xQueueCreate(2, sizeof(ChunkUploadJob));

  if (!g_bufASem || !g_bufBSem || !g_uploadQueue) {
    Serial.println("FATAL: queue/semaphore init failed");
    while (true) delay(1000);
  }
  xSemaphoreGive(g_bufASem);
  xSemaphoreGive(g_bufBSem);

  xTaskCreatePinnedToCore(uploaderTask, "uploader", 8192, nullptr, 1, &g_uploaderTaskHandle, 1);

  Serial.printf("[MEM] chunk_bytes=%d (~%d sec) free_heap=%d\n", CHUNK_BYTES, CHUNK_SECONDS, ESP.getFreeHeap());
  Serial.printf("[CFG] target_chunk_sec=%d backend_max_chunk_bytes=%d\n", TARGET_CHUNK_SECONDS, BACKEND_MAX_CHUNK_BYTES);
  if (AUTO_ROLLING_FINALIZE) {
    Serial.printf("[CFG] auto_finalize_after_chunks=%lu (~%lu sec)\n",
                  static_cast<unsigned long>(AUTO_FINALIZE_AFTER_CHUNKS),
                  static_cast<unsigned long>((AUTO_FINALIZE_AFTER_CHUNKS * CHUNK_MS) / 1000));
  } else {
    Serial.println("[CFG] auto_finalize=OFF (manual stop required)");
  }

  if (!ensureWiFi()) {
    Serial.println("[NET] Initial WiFi connect failed. Will retry in loop.");
  }

  if (!initMic()) {
    Serial.println("[MIC] FATAL: mic init failed");
    while (true) delay(1000);
  }

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

  if (!g_isPaired) {
    if (millis() - g_lastNotPairedLogMs > 5000) {
      Serial.println("[PAIR] Waiting for pairing. Send 'p' to enter pairing mode.");
      g_lastNotPairedLogMs = millis();
    }
    delay(20);
    return;
  }

  if (g_streamFault) {
    Serial.println("[REC] Stream fault detected; stopping stream and finalizing current session");
    g_streamFault = false;
    g_autoStream = false;
    requestFinalize("stream_fault");
  }

  if (g_finalizeRequested) {
    g_finalizeRequested = false;
    if (!stopAndFinalizeSession(g_finalizeReason)) {
      delay(500);
    }
  }

  if (!g_autoStream) {
    delay(20);
    return;
  }

  Serial.println("══════════════════════════════");
  Serial.printf("[MEM] free_heap=%d active_session=%s next_chunk=%lu\n",
                ESP.getFreeHeap(),
                g_activeSessionId.isEmpty() ? "none" : g_activeSessionId.c_str(),
                static_cast<unsigned long>(g_nextChunkIndex));

  if (!runContinuousChunkOnce()) {
    delay(800);
  }
}
