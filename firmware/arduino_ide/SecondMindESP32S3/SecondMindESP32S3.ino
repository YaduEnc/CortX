#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <Preferences.h>
#include <driver/i2s.h>
#include <esp_heap_caps.h>
#include <esp_system.h>
#include <vector>


// Wi-Fi
#define WIFI_SSID "Yadu Phone"
#define WIFI_PASSWORD "0000110000"

// Backend
// Keep NO trailing slash.
#define API_BASE_URL "https://hamza.yaduraj.me/v1"

// Device credentials (created via POST /v1/device/register)
#define DEVICE_CODE "esp32s3-dev-01"
#define DEVICE_SECRET "change-this-device-secret"

// Device identity visible in BLE
#define DEVICE_BLE_NAME "SecondMind-ESP32S3-01"

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
// ======================================================================

static const char *PAIR_SERVICE_UUID = "8b6ad1ca-c85d-4262-b1f6-85e134fdb2f0";
static const char *DEVICE_INFO_CHAR_UUID = "94dcbd89-0f5a-4fb3-9f61-a3d2664d35d1";
static const char *PAIR_NONCE_CHAR_UUID = "2dc45f2c-5924-48cf-a615-f9e3c1070ad4";
static const char *PAIR_TOKEN_CHAR_UUID = "9f8b48ad-e983-4abf-8b56-53f31c0f7596";
static const char *PAIR_STATUS_CHAR_UUID = "ea85f9b1-1c57-4fdd-95ac-5c92b8a07b3d";

static const uint32_t PAIR_MODE_WINDOW_MS = 120000;
static const uint32_t LONG_PRESS_MS = 5000;

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

constexpr i2s_port_t I2S_PORT = I2S_NUM_0;
constexpr size_t CHUNK_BYTES = (SAMPLE_RATE_HZ * CHUNK_DURATION_MS / 1000) * (SAMPLE_BITS / 8) * CHANNELS;

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
  char buf[9] = {0};
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
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  Serial.printf("[WIFI] Connecting to %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 30000) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WIFI] Failed to connect");
    return false;
  }

  Serial.printf("[WIFI] Connected, IP=%s\n", WiFi.localIP().toString().c_str());
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

  std::vector<uint8_t> body;
  body.resize(pre.length() + audioLen + post.length());
  memcpy(body.data(), pre.c_str(), pre.length());
  memcpy(body.data() + pre.length(), audio, audioLen);
  memcpy(body.data() + pre.length() + audioLen, post.c_str(), post.length());

  http.addHeader("Authorization", "Bearer " + g_deviceJwt);
  http.addHeader("Content-Type", "multipart/form-data; boundary=" + boundary);

  int code = http.POST(body.data(), body.size());
  String response = http.getString();
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
  i2s_config_t i2sConfig = {};
  i2sConfig.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_RX);
#if MIC_MODE_PDM
  i2sConfig.mode = static_cast<i2s_mode_t>(i2sConfig.mode | I2S_MODE_PDM);
#endif
  i2sConfig.sample_rate = SAMPLE_RATE_HZ;
  i2sConfig.bits_per_sample = static_cast<i2s_bits_per_sample_t>(SAMPLE_BITS);
  i2sConfig.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  i2sConfig.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  i2sConfig.intr_alloc_flags = 0;
  i2sConfig.dma_buf_count = 8;
  i2sConfig.dma_buf_len = 512;
  i2sConfig.use_apll = false;
  i2sConfig.tx_desc_auto_clear = false;
  i2sConfig.fixed_mclk = 0;
#ifdef I2S_MCLK_MULTIPLE_DEFAULT
  i2sConfig.mclk_multiple = I2S_MCLK_MULTIPLE_DEFAULT;
#endif
#ifdef I2S_BITS_PER_CHAN_DEFAULT
  i2sConfig.bits_per_chan = I2S_BITS_PER_CHAN_DEFAULT;
#endif

  i2s_pin_config_t pinConfig = {
      .bck_io_num = (I2S_BCLK_PIN >= 0) ? I2S_BCLK_PIN : I2S_PIN_NO_CHANGE,
      .ws_io_num = (I2S_WS_PIN >= 0) ? I2S_WS_PIN : I2S_PIN_NO_CHANGE,
      .data_out_num = I2S_PIN_NO_CHANGE,
      .data_in_num = (I2S_DATA_IN_PIN >= 0) ? I2S_DATA_IN_PIN : I2S_PIN_NO_CHANGE,
  };

  if (i2s_driver_install(I2S_PORT, &i2sConfig, 0, nullptr) != ESP_OK) {
    Serial.println("[I2S] driver install failed");
    return false;
  }

  if (i2s_set_pin(I2S_PORT, &pinConfig) != ESP_OK) {
    Serial.println("[I2S] set pin failed");
    return false;
  }

  i2s_zero_dma_buffer(I2S_PORT);
  Serial.println("[I2S] initialized");
  return true;
}

bool readPcmChunk(uint8_t *out, size_t expectedBytes) {
  size_t total = 0;
  while (total < expectedBytes) {
    size_t bytesRead = 0;
    esp_err_t err = i2s_read(I2S_PORT, out + total, expectedBytes - total, &bytesRead, pdMS_TO_TICKS(2000));
    if (err != ESP_OK) {
      Serial.printf("[I2S] read error=%d\n", static_cast<int>(err));
      return false;
    }
    total += bytesRead;
  }
  return true;
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
#ifdef MALLOC_CAP_SPIRAM
    chunkBuffer = static_cast<uint8_t *>(heap_caps_malloc(CHUNK_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
#endif
    if (!chunkBuffer) {
      chunkBuffer = static_cast<uint8_t *>(malloc(CHUNK_BYTES));
    }
    if (!chunkBuffer) {
      Serial.println("[CAPTURE] chunk buffer alloc failed");
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
      g_captureRequested = true;
    } else {
      setPairStatus("failed");
    }
  }
}

void printSerialHelp() {
  Serial.println("\n=== SecondMind ESP32 Commands ===");
  Serial.println("p : enter pairing mode");
  Serial.println("r : run one capture session now");
  Serial.println("u : re-auth device");
  Serial.println("x : clear paired flag");
  Serial.println("=================================\n");
}

void handleSerialCommands() {
  while (Serial.available()) {
    char c = static_cast<char>(Serial.read());
    if (c == 'p') {
      enterPairingMode();
    } else if (c == 'r') {
      g_captureRequested = true;
    } else if (c == 'u') {
      authDevice();
    } else if (c == 'x') {
      g_isPaired = false;
      g_prefs.putBool("paired", false);
      Serial.println("[PAIR] paired flag cleared");
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

  delay(20);
}
