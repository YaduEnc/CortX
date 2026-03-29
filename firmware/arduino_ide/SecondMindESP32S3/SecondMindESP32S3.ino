#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <ESP_I2S.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <Preferences.h>
#include <esp_heap_caps.h>
#include <esp_system.h>


#define WIFI_SSID "Yadu Phone"
#define WIFI_PASSWORD "0000110000"

// Backend
// Keep NO trailing slash.
#define API_BASE_URL "https://hamza.yaduraj.me/v1"


#define DEVICE_CODE "manu"
#define DEVICE_SECRET "1234567890"


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
// 1s chunk keeps RAM use stable on ESP32-S3 while still low latency.
#define CHUNK_DURATION_MS 1000
#define CAPTURE_CHUNKS_PER_SESSION 3

// Testing mode
// When true and device is not paired, pairing mode starts automatically on boot.
#define TEST_MODE_AUTO_PAIR_ON_BOOT true
// ======================================================================

static const char *PAIR_SERVICE_UUID = "8b6ad1ca-c85d-4262-b1f6-85e134fdb2f0";
static const char *DEVICE_INFO_CHAR_UUID = "94dcbd89-0f5a-4fb3-9f61-a3d2664d35d1";
static const char *PAIR_NONCE_CHAR_UUID = "2dc45f2c-5924-48cf-a615-f9e3c1070ad4";
static const char *PAIR_TOKEN_CHAR_UUID = "9f8b48ad-e983-4abf-8b56-53f31c0f7596";
static const char *PAIR_STATUS_CHAR_UUID = "ea85f9b1-1c57-4fdd-95ac-5c92b8a07b3d";

static const uint32_t PAIR_MODE_WINDOW_MS = 300000;
static const uint32_t LONG_PRESS_MS = 5000;
static const uint32_t WIFI_CONNECT_TIMEOUT_MS = 30000;

static BLEServer *g_bleServer = nullptr;
static BLEService *g_pairService = nullptr;
static BLECharacteristic *g_deviceInfoChar = nullptr;
static BLECharacteristic *g_pairNonceChar = nullptr;
static BLECharacteristic *g_pairTokenChar = nullptr;
static BLECharacteristic *g_pairStatusChar = nullptr;

static Preferences g_prefs;

static String g_deviceJwt;
static String g_pairNonce;
static String g_pairTokenFromApp;
static bool g_pairTokenReady = false;
static bool g_isPairingMode = false;
static bool g_isPaired = false;

static uint32_t g_pairModeEndAt = 0;
static uint32_t g_buttonPressedAt = 0;
static bool g_buttonWasDown = false;

static bool g_captureRequested = false;
static volatile bool g_wifiConnectInProgress = false;
static bool g_recordingActive = false;
static String g_liveSessionId = "";
static int g_liveChunkIndex = 0;
static uint32_t g_liveChunkStartMs = 0;
static volatile bool g_stopRecordingRequested = false;

constexpr size_t CHUNK_BYTES = (SAMPLE_RATE_HZ * CHUNK_DURATION_MS / 1000) * (SAMPLE_BITS / 8) * CHANNELS;
static I2SClass g_i2s;

String apiUrl(const String &path) {
  return String(API_BASE_URL) + path;
}

String generateNonceHex(size_t bytesLen) {
  static const char *hex = "0123456789abcdef";
  String out;
  out.reserve(bytesLen * 2);
  for (size_t i = 0; i < bytesLen; i++) {
    uint8_t b = static_cast<uint8_t>(esp_random() & 0xFF);
    out += hex[(b >> 4) & 0x0F];
    out += hex[b & 0x0F];
  }
  return out;
}

uint32_t crc32(const uint8_t *data, size_t len) {
  uint32_t crc = 0xFFFFFFFF;
  for (size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (int j = 0; j < 8; ++j) {
      crc = (crc >> 1) ^ (0xEDB88320 & (-(int)(crc & 1)));
    }
  }
  return ~crc;
}

String toHex8(uint32_t value) {
  char buf[9] = { 0 };
  snprintf(buf, sizeof(buf), "%08x", value);
  return String(buf);
}

void setPairStatus(const String &status) {
  if (!g_pairStatusChar) {
    return;
  }
  g_pairStatusChar->setValue(status.c_str());
  g_pairStatusChar->notify();
  Serial.printf("[PAIR] status=%s\n", status.c_str());
}

class PairTokenCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    String value = characteristic->getValue();
    if (value.length() == 0) {
      return;
    }

    g_pairTokenFromApp = value;
    g_pairTokenReady = true;
    Serial.println("[PAIR] Received pair_token over BLE");
    setPairStatus("token_received");
  }
};

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

  StaticJsonDocument<160> infoDoc;
  infoDoc["device_code"] = DEVICE_CODE;
  infoDoc["fw_version"] = "1.0.0";
  infoDoc["model"] = "ESP32-S3";

  String infoJson;
  serializeJson(infoDoc, infoJson);
  g_deviceInfoChar->setValue(infoJson.c_str());
  g_pairNonceChar->setValue("not_in_pair_mode");
  g_pairStatusChar->setValue("idle");

  g_pairService->start();
}

void enterPairingMode() {
  g_pairNonce = generateNonceHex(16);
  g_pairTokenFromApp = "";
  g_pairTokenReady = false;
  g_pairModeEndAt = millis() + PAIR_MODE_WINDOW_MS;
  g_isPairingMode = true;

  g_pairNonceChar->setValue(g_pairNonce.c_str());
  setPairStatus("pairing_mode");

  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(PAIR_SERVICE_UUID);
  advertising->setScanResponse(true);
  advertising->setMinPreferred(0x06);
  advertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();

  Serial.printf("[PAIR] Pairing mode ON nonce=%s\n", g_pairNonce.c_str());
}

void exitPairingMode(const String &finalStatus) {
  g_isPairingMode = false;
  BLEDevice::stopAdvertising();
  setPairStatus(finalStatus);
  Serial.printf("[PAIR] Pairing mode OFF status=%s\n", finalStatus.c_str());
}

bool ensureWifiConnected() {
  if (g_wifiConnectInProgress) {
    uint32_t waitStarted = millis();
    while (g_wifiConnectInProgress && millis() - waitStarted < WIFI_CONNECT_TIMEOUT_MS + 2000) {
      delay(50);
    }
  }

  if (WiFi.status() == WL_CONNECTED && WiFi.SSID() == String(WIFI_SSID)) {
    return true;
  }

  if (g_wifiConnectInProgress) {
    Serial.println("[WIFI] Connection already in progress; skipping duplicate request");
    return false;
  }

  g_wifiConnectInProgress = true;

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.disconnect(true, true);
  delay(350);

  Serial.printf("[WIFI] Connecting to %s\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < WIFI_CONNECT_TIMEOUT_MS) {
    wl_status_t st = WiFi.status();
    if (st == WL_CONNECT_FAILED || st == WL_NO_SSID_AVAIL || st == WL_CONNECTION_LOST) {
      break;
    }
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WIFI] Failed to connect");
    g_wifiConnectInProgress = false;
    return false;
  }

  Serial.printf("[WIFI] Connected, IP=%s\n", WiFi.localIP().toString().c_str());
  g_wifiConnectInProgress = false;
  return true;
}

bool postJson(const String &url,
              const String &payload,
              String &response,
              const String &bearer = "",
              int *statusCode = nullptr) {
  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  if (!http.begin(client, url)) {
    Serial.printf("[HTTP] begin failed for %s\n", url.c_str());
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  if (!bearer.isEmpty()) {
    http.addHeader("Authorization", "Bearer " + bearer);
  }

  int code = http.POST(payload);
  response = http.getString();
  if (statusCode) {
    *statusCode = code;
  }

  http.end();
  return code > 0;
}

bool authDevice() {
  if (!ensureWifiConnected()) {
    return false;
  }

  StaticJsonDocument<256> doc;
  doc["device_code"] = DEVICE_CODE;
  doc["secret"] = DEVICE_SECRET;

  String payload;
  serializeJson(doc, payload);

  String response;
  int code = 0;
  if (!postJson(apiUrl("/device/auth"), payload, response, "", &code)) {
    Serial.println("[AUTH] HTTP request failed");
    return false;
  }

  if (code != 200) {
    Serial.printf("[AUTH] Failed code=%d body=%s\n", code, response.c_str());
    return false;
  }

  DynamicJsonDocument out(1024);
  if (deserializeJson(out, response)) {
    Serial.println("[AUTH] JSON parse failed");
    return false;
  }

  g_deviceJwt = String((const char *)out["access_token"]);
  if (g_deviceJwt.isEmpty()) {
    Serial.println("[AUTH] Missing access_token");
    return false;
  }

  Serial.println("[AUTH] Device JWT acquired");
  return true;
}

bool completePairingWithBackend(const String &pairToken) {
  if (g_deviceJwt.isEmpty() && !authDevice()) {
    return false;
  }

  StaticJsonDocument<256> doc;
  doc["pair_token"] = pairToken;

  String payload;
  serializeJson(doc, payload);

  String response;
  int code = 0;
  if (!postJson(apiUrl("/device/pairing/complete"), payload, response, g_deviceJwt, &code)) {
    Serial.println("[PAIR] complete request failed");
    return false;
  }

  if (code != 200) {
    Serial.printf("[PAIR] complete failed code=%d body=%s\n", code, response.c_str());
    return false;
  }

  g_isPaired = true;
  g_prefs.putBool("paired", true);
  Serial.println("[PAIR] Device paired successfully");
  return true;
}

bool createCaptureSession(String &sessionIdOut) {
  StaticJsonDocument<256> doc;
  doc["sample_rate"] = SAMPLE_RATE_HZ;
  doc["channels"] = CHANNELS;
  doc["codec"] = "pcm16le";

  String payload;
  serializeJson(doc, payload);

  String response;
  int code = 0;
  if (!postJson(apiUrl("/capture/sessions"), payload, response, g_deviceJwt, &code)) {
    return false;
  }

  if (code != 201) {
    Serial.printf("[CAPTURE] create session failed code=%d body=%s\n", code, response.c_str());
    return false;
  }

  DynamicJsonDocument out(1024);
  if (deserializeJson(out, response)) {
    return false;
  }

  sessionIdOut = String((const char *)out["session_id"]);
  return !sessionIdOut.isEmpty();
}

bool uploadChunkMultipart(const String &sessionId,
                          int chunkIndex,
                          uint32_t startMs,
                          uint32_t endMs,
                          const uint8_t *audio,
                          size_t audioLen) {
  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  String url = apiUrl("/capture/chunks");
  if (!http.begin(client, url)) {
    return false;
  }

  String boundary = "----SecondMindBoundary7e3f93";
  String crc = toHex8(crc32(audio, audioLen));

  String pre = "";
  pre += "--" + boundary + "\r\n";
  pre += "Content-Disposition: form-data; name=\"session_id\"\r\n\r\n" + sessionId + "\r\n";
  pre += "--" + boundary + "\r\n";
  pre += "Content-Disposition: form-data; name=\"chunk_index\"\r\n\r\n" + String(chunkIndex) + "\r\n";
  pre += "--" + boundary + "\r\n";
  pre += "Content-Disposition: form-data; name=\"start_ms\"\r\n\r\n" + String(startMs) + "\r\n";
  pre += "--" + boundary + "\r\n";
  pre += "Content-Disposition: form-data; name=\"end_ms\"\r\n\r\n" + String(endMs) + "\r\n";
  pre += "--" + boundary + "\r\n";
  pre += "Content-Disposition: form-data; name=\"sample_rate\"\r\n\r\n" + String(SAMPLE_RATE_HZ) + "\r\n";
  pre += "--" + boundary + "\r\n";
  pre += "Content-Disposition: form-data; name=\"channels\"\r\n\r\n" + String(CHANNELS) + "\r\n";
  pre += "--" + boundary + "\r\n";
  pre += "Content-Disposition: form-data; name=\"codec\"\r\n\r\npcm16le\r\n";
  pre += "--" + boundary + "\r\n";
  pre += "Content-Disposition: form-data; name=\"crc32\"\r\n\r\n" + crc + "\r\n";
  pre += "--" + boundary + "\r\n";
  pre += "Content-Disposition: form-data; name=\"audio_file\"; filename=\"chunk.pcm\"\r\n";
  pre += "Content-Type: application/octet-stream\r\n\r\n";

  String post = "\r\n--" + boundary + "--\r\n";

  size_t bodyLen = pre.length() + audioLen + post.length();
  uint8_t *body = nullptr;
#ifdef MALLOC_CAP_SPIRAM
  body = static_cast<uint8_t *>(heap_caps_malloc(bodyLen, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
#endif
  if (!body) {
    body = static_cast<uint8_t *>(malloc(bodyLen));
  }
  if (!body) {
    Serial.printf("[CAPTURE] multipart alloc failed bytes=%u\n", static_cast<unsigned>(bodyLen));
    http.end();
    return false;
  }

  memcpy(body, pre.c_str(), pre.length());
  memcpy(body + pre.length(), audio, audioLen);
  memcpy(body + pre.length() + audioLen, post.c_str(), post.length());

  http.addHeader("Authorization", "Bearer " + g_deviceJwt);
  http.addHeader("Content-Type", "multipart/form-data; boundary=" + boundary);

  int code = http.POST(body, bodyLen);
  String response = http.getString();

  free(body);
  http.end();

  if (code != 200) {
    Serial.printf("[CAPTURE] upload failed idx=%d code=%d body=%s\n", chunkIndex, code, response.c_str());
    return false;
  }

  Serial.printf("[CAPTURE] upload success idx=%d\n", chunkIndex);
  return true;
}

bool finalizeSession(const String &sessionId) {
  String response;
  int code = 0;
  if (!postJson(apiUrl("/capture/sessions/") + sessionId + "/finalize", "", response, g_deviceJwt, &code)) {
    return false;
  }

  if (code != 200) {
    Serial.printf("[CAPTURE] finalize failed code=%d body=%s\n", code, response.c_str());
    return false;
  }

  Serial.printf("[CAPTURE] finalize success session=%s\n", sessionId.c_str());
  return true;
}

bool initI2S() {
  g_i2s.end();
#if MIC_MODE_PDM
  g_i2s.setPinsPdmRx(I2S_WS_PIN, I2S_DATA_IN_PIN);
  if (!g_i2s.begin(I2S_MODE_PDM_RX, SAMPLE_RATE_HZ, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO)) {
    Serial.println("[I2S] begin PDM RX failed");
    return false;
  }
#else
  g_i2s.setPins(I2S_BCLK_PIN, I2S_WS_PIN, -1, I2S_DATA_IN_PIN, -1);
  if (!g_i2s.begin(I2S_MODE_STD, SAMPLE_RATE_HZ, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO)) {
    Serial.println("[I2S] begin STD RX failed");
    return false;
  }
#endif

  Serial.println("[I2S] initialized");
  return true;
}

bool readPcmChunk(uint8_t *out, size_t expectedBytes, bool allowStopRequest = false) {
  size_t total = 0;
  int idleReads = 0;
  while (total < expectedBytes) {
    if (allowStopRequest && g_stopRecordingRequested) {
      return false;
    }

    int availableBytes = g_i2s.available();
    if (availableBytes <= 0) {
      idleReads++;
      if (idleReads >= 100) {
        Serial.println("[I2S] no mic data / read timeout (check Sense mic board seating + GPIO42 CLK, GPIO41 DATA)");
        return false;
      }
      delay(10);
      continue;
    }

    size_t maxWanted = expectedBytes - total;
    size_t wanted = static_cast<size_t>(availableBytes);
    if (wanted > maxWanted) {
      wanted = maxWanted;
    }

    size_t bytesRead = g_i2s.readBytes(reinterpret_cast<char *>(out + total), wanted);
    if (bytesRead == 0) {
      idleReads++;
      if (idleReads >= 25) {
        Serial.println("[I2S] no mic data / read timeout (check Sense mic board seating + GPIO42 CLK, GPIO41 DATA)");
        return false;
      }
      delay(1);
      continue;
    }

    idleReads = 0;
    total += bytesRead;
  }
  return true;
}

uint8_t *allocateI2SReadBuffer(size_t bytes) {
  uint8_t *buf = nullptr;
#ifdef MALLOC_CAP_DMA
  buf = static_cast<uint8_t *>(heap_caps_malloc(bytes, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  if (buf) {
    return buf;
  }
#endif
  buf = static_cast<uint8_t *>(heap_caps_malloc(bytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  if (buf) {
    return buf;
  }
  return static_cast<uint8_t *>(malloc(bytes));
}

bool runCaptureSession() {
  if (!g_isPaired) {
    Serial.println("[CAPTURE] not paired; skipping");
    return false;
  }

  if (g_deviceJwt.isEmpty() && !authDevice()) {
    return false;
  }

  String sessionId;
  if (!createCaptureSession(sessionId)) {
    Serial.println("[CAPTURE] create session failed");
    return false;
  }

  Serial.printf("[CAPTURE] session=%s\n", sessionId.c_str());

  static uint8_t *chunkBuffer = nullptr;
  if (!chunkBuffer) {
    chunkBuffer = allocateI2SReadBuffer(CHUNK_BYTES);
    if (!chunkBuffer) {
      Serial.println("[CAPTURE] chunk buffer alloc failed (try reducing CHUNK_DURATION_MS)");
      return false;
    }
  }

  uint32_t startMs = 0;
  for (int i = 0; i < CAPTURE_CHUNKS_PER_SESSION; i++) {
    if (!readPcmChunk(chunkBuffer, CHUNK_BYTES)) {
      return false;
    }

    uint32_t endMs = startMs + CHUNK_DURATION_MS;
    if (!uploadChunkMultipart(sessionId, i, startMs, endMs, chunkBuffer, CHUNK_BYTES)) {
      return false;
    }

    startMs = endMs;
  }

  return finalizeSession(sessionId);
}

bool startLiveRecording() {
  if (g_recordingActive) {
    Serial.println("[REC] already recording");
    return true;
  }

  if (!g_isPaired) {
    Serial.println("[REC] device not paired");
    return false;
  }

  if (!ensureWifiConnected()) {
    Serial.println("[REC] Wi-Fi not connected");
    return false;
  }

  if (g_deviceJwt.isEmpty() && !authDevice()) {
    Serial.println("[REC] device auth failed");
    return false;
  }

  String sessionId;
  if (!createCaptureSession(sessionId)) {
    Serial.println("[REC] create session failed");
    return false;
  }

  g_liveSessionId = sessionId;
  g_liveChunkIndex = 0;
  g_liveChunkStartMs = 0;
  g_recordingActive = true;

  Serial.printf("[REC] started session=%s chunk_ms=%d\n", g_liveSessionId.c_str(), CHUNK_DURATION_MS);
  return true;
}

void stopLiveRecording(bool dueToError = false) {
  if (!g_recordingActive) {
    Serial.println("[REC] not recording");
    return;
  }

  if (dueToError) {
    Serial.printf("[REC] stopped due to error, session=%s\n", g_liveSessionId.c_str());
    g_recordingActive = false;
    g_liveSessionId = "";
    g_liveChunkIndex = 0;
    g_liveChunkStartMs = 0;
    return;
  }

  if (!finalizeSession(g_liveSessionId)) {
    Serial.println("[REC] finalize failed");
  } else {
    Serial.printf("[REC] stopped + finalized session=%s total_chunks=%d\n",
                  g_liveSessionId.c_str(),
                  g_liveChunkIndex);
  }

  g_recordingActive = false;
  g_liveSessionId = "";
  g_liveChunkIndex = 0;
  g_liveChunkStartMs = 0;
}

bool processLiveRecordingChunk() {
  if (!g_recordingActive) {
    return true;
  }

  if (g_stopRecordingRequested) {
    g_stopRecordingRequested = false;
    stopLiveRecording(false);
    return true;
  }

  static uint8_t *chunkBuffer = nullptr;
  if (!chunkBuffer) {
    chunkBuffer = allocateI2SReadBuffer(CHUNK_BYTES);
    if (!chunkBuffer) {
      Serial.println("[REC] chunk buffer alloc failed (try reducing CHUNK_DURATION_MS)");
      return false;
    }
  }

  if (!ensureWifiConnected()) {
    Serial.println("[REC] Wi-Fi dropped");
    return false;
  }

  if (g_deviceJwt.isEmpty() && !authDevice()) {
    Serial.println("[REC] auth failed");
    return false;
  }

  if (!readPcmChunk(chunkBuffer, CHUNK_BYTES, true)) {
    if (g_stopRecordingRequested) {
      g_stopRecordingRequested = false;
      stopLiveRecording(false);
      return true;
    }
    Serial.println("[REC] audio read failed");
    return false;
  }

  uint32_t chunkEndMs = g_liveChunkStartMs + CHUNK_DURATION_MS;
  bool ok = uploadChunkMultipart(
    g_liveSessionId,
    g_liveChunkIndex,
    g_liveChunkStartMs,
    chunkEndMs,
    chunkBuffer,
    CHUNK_BYTES
  );

  if (!ok) {
    if (g_stopRecordingRequested) {
      g_stopRecordingRequested = false;
      stopLiveRecording(false);
      return true;
    }
    Serial.printf("[REC] upload failed chunk=%d\n", g_liveChunkIndex);
    return false;
  }

  Serial.printf("[REC] uploaded chunk=%d ms=%u-%u\n", g_liveChunkIndex, g_liveChunkStartMs, chunkEndMs);
  g_liveChunkIndex++;
  g_liveChunkStartMs = chunkEndMs;
  return true;
}

void handlePairButton() {
#if PAIR_BUTTON_PIN < 0
  return;
#endif

  bool down = digitalRead(PAIR_BUTTON_PIN) == LOW;

  if (down && !g_buttonWasDown) {
    g_buttonPressedAt = millis();
  }

  if (!down && g_buttonWasDown) {
    g_buttonPressedAt = 0;
  }

  g_buttonWasDown = down;

  if (down && g_buttonPressedAt > 0 && (millis() - g_buttonPressedAt) >= LONG_PRESS_MS && !g_isPairingMode) {
    enterPairingMode();
    g_buttonPressedAt = 0;
  }
}

void handlePairingState() {
  if (!g_isPairingMode) {
    return;
  }

  if (millis() > g_pairModeEndAt) {
    exitPairingMode("expired");
    return;
  }

  if (g_pairTokenReady) {
    g_pairTokenReady = false;
    setPairStatus("validating");

    if (completePairingWithBackend(g_pairTokenFromApp)) {
      exitPairingMode("success");
      Serial.println("[PAIR] Pair complete. Use 's' to start live recording.");
    } else {
      setPairStatus("failed");
    }
  }
}

void printSerialHelp() {
  Serial.println("\n=== SecondMind ESP32 Commands ===");
  Serial.println("p : enter pairing mode");
  Serial.println("r : run one capture session now");
  Serial.println("s : start live recording (continuous upload)");
  Serial.println("t : stop live recording and finalize session");
  Serial.println("u : re-auth device");
  Serial.println("x : clear paired flag");
  Serial.println("h : show this help");
  Serial.println("=================================\n");
}

void handleSerialCommands() {
  while (Serial.available()) {
    char c = static_cast<char>(Serial.read());
    if (c == 'p') {
      enterPairingMode();
    } else if (c == 'r') {
      g_captureRequested = true;
    } else if (c == 's') {
      startLiveRecording();
    } else if (c == 't') {
      if (g_recordingActive) {
        g_stopRecordingRequested = true;
        Serial.println("[REC] stop requested");
      } else {
        stopLiveRecording(false);
      }
    } else if (c == 'u') {
      authDevice();
    } else if (c == 'x') {
      g_isPaired = false;
      g_prefs.putBool("paired", false);
      Serial.println("[PAIR] paired flag cleared");
    } else if (c == 'h') {
      printSerialHelp();
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);

#if PAIR_BUTTON_PIN >= 0
  pinMode(PAIR_BUTTON_PIN, INPUT_PULLUP);
#endif

  g_prefs.begin("secondmind", false);
  g_isPaired = g_prefs.getBool("paired", false);

  setupBle();
  ensureWifiConnected();
  initI2S();

  if (g_isPaired) {
    Serial.println("[BOOT] Device already paired (from NVS)");
    authDevice();
  } else {
    Serial.println("[BOOT] Device not paired yet.");
#if TEST_MODE_AUTO_PAIR_ON_BOOT
    Serial.println("[BOOT] TEST_MODE_AUTO_PAIR_ON_BOOT=true, entering pairing mode.");
    enterPairingMode();
#else
    Serial.println("[BOOT] Long-press button for pairing mode.");
#endif
  }

  printSerialHelp();
}

void loop() {
  handleSerialCommands();
  handlePairButton();
  handlePairingState();

  if (g_captureRequested) {
    g_captureRequested = false;
    if (!runCaptureSession()) {
      Serial.println("[CAPTURE] session failed");
    }
  }

  if (g_recordingActive) {
    if (!processLiveRecordingChunk()) {
      stopLiveRecording(true);
    }
  }

  delay(20);
}
