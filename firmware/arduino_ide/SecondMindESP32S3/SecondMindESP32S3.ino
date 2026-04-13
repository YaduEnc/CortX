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
#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "config.h"

// Note: Values are now loaded from config.h
// ============================================================================
// UUIDs
// ============================================================================
static const char *PAIR_SERVICE_UUID = "8b6ad1ca-c85d-4262-b1f6-85e134fdb2f0";
static const char *DEVICE_INFO_CHAR_UUID = "94dcbd89-0f5a-4fb3-9f61-a3d2664d35d1";
static const char *PAIR_NONCE_CHAR_UUID = "2dc45f2c-5924-48cf-a615-f9e3c1070ad4";
static const char *PAIR_TOKEN_CHAR_UUID = "9f8b48ad-e983-4abf-8b56-53f31c0f7596";
static const char *PAIR_STATUS_CHAR_UUID = "ea85f9b1-1c57-4fdd-95ac-5c92b8a07b3d";

static const char *AUDIO_CONTROL_CHAR_UUID = "d413d6c7-2d5f-4f04-8dd1-d0cd9cbdc1f1";
static const char *AUDIO_DATA_CHAR_UUID = "8f7f3b93-9b0f-4fcb-8a0c-0e7f4e4fd2d1";
static const char *AUDIO_STATE_CHAR_UUID = "5e0f6d5f-cf6e-4dc5-9fca-2fa2a3434f4a";

// ============================================================================
// TIMING
// ============================================================================
static const uint32_t PAIR_MODE_WINDOW_MS = 300000;
static const uint32_t LONG_PRESS_MS = 5000;
static const uint32_t WIFI_CONNECT_TIMEOUT_MS = 30000;

// ============================================================================
// BLE / PREFS GLOBALS
// ============================================================================
static BLEServer *g_bleServer = nullptr;
static BLEService *g_pairService = nullptr;
static BLECharacteristic *g_deviceInfoChar = nullptr;
static BLECharacteristic *g_pairNonceChar = nullptr;
static BLECharacteristic *g_pairTokenChar = nullptr;
static BLECharacteristic *g_pairStatusChar = nullptr;
static BLECharacteristic *g_audioControlChar = nullptr;
static BLECharacteristic *g_audioDataChar = nullptr;
static BLECharacteristic *g_audioStateChar = nullptr;

static Preferences g_prefs;

// ============================================================================
// STATE GLOBALS
// ============================================================================
static String g_deviceJwt;
static String g_pairNonce;
static String g_pairTokenFromApp;

static bool g_pairTokenReady = false;
static bool g_isPairingMode = false;
static bool g_isPaired = false;

static uint32_t g_pairModeEndAt = 0;
static uint32_t g_buttonPressedAt = 0;
static bool g_buttonWasDown = false;

static volatile bool g_recordingActive = false;
static volatile bool g_stopRecordingRequested = false;
static uint32_t g_blePacketSeq = 0;

static float g_dcPrevX = 0.0f;
static float g_dcPrevY = 0.0f;

static I2SClass g_i2s;
static TaskHandle_t g_recTaskHandle = nullptr;
static bool g_advConfigured = false;

// ============================================================================
// FORWARD DECLARATIONS
// ============================================================================
bool startLiveRecording();
void stopLiveRecording(bool dueToError);
void startBleAdvertising();
void stopBleAdvertising();

// ============================================================================
// HELPERS
// ============================================================================
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

void setPairStatus(const String &status) {
  if (!g_pairStatusChar) return;
  g_pairStatusChar->setValue(status.c_str());
  g_pairStatusChar->notify();
  Serial.printf("[PAIR] status=%s\n", status.c_str());
}

void setAudioState(const String &status) {
  if (!g_audioStateChar) return;
  g_audioStateChar->setValue(status.c_str());
  g_audioStateChar->notify();
  Serial.printf("[AUDIO] state=%s\n", status.c_str());
}

// ============================================================================
// WIFI + HTTP
// ============================================================================
bool ensureWifiConnected() {
  if (WiFi.status() == WL_CONNECTED && WiFi.SSID() == String(WIFI_SSID)) {
    return true;
  }

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.disconnect(true, true);
  delay(300);

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
    Serial.println("[WIFI] failed");
    return false;
  }

  Serial.printf("[WIFI] connected, IP=%s\n", WiFi.localIP().toString().c_str());
  return true;
}

bool postJson(const String &url, const String &payload, String &response, const String &bearer = "", int *statusCode = nullptr) {
  if (!ensureWifiConnected()) {
    return false;
  }

  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;

  if (!http.begin(client, url)) {
    Serial.printf("[HTTP] begin failed url=%s\n", url.c_str());
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  if (!bearer.isEmpty()) {
    http.addHeader("Authorization", "Bearer " + bearer);
  }

  int code = http.POST(payload);
  response = http.getString();
  if (statusCode) *statusCode = code;
  http.end();
  return code > 0;
}

bool authDevice() {
  StaticJsonDocument<256> doc;
  doc["device_code"] = DEVICE_CODE;
  doc["secret"] = DEVICE_SECRET;
  String payload;
  serializeJson(doc, payload);

  String response;
  int code = 0;
  if (!postJson(apiUrl("/device/auth"), payload, response, "", &code)) {
    Serial.println("[AUTH] request failed");
    return false;
  }
  if (code != 200) {
    Serial.printf("[AUTH] failed code=%d body=%s\n", code, response.c_str());
    return false;
  }

  DynamicJsonDocument out(1024);
  if (deserializeJson(out, response)) {
    Serial.println("[AUTH] parse failed");
    return false;
  }

  const char *token = out["access_token"];
  if (!token || String(token).isEmpty()) {
    Serial.println("[AUTH] missing token");
    return false;
  }

  g_deviceJwt = String(token);
  Serial.println("[AUTH] device JWT acquired");
  return true;
}

bool completePairingWithBackend(const String &pairToken) {
  if (pairToken.isEmpty()) return false;

  if (g_deviceJwt.isEmpty() && !authDevice()) {
    Serial.println("[PAIR] auth failed before complete");
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
  Serial.println("[PAIR] device paired successfully");
  return true;
}

// ============================================================================
// BLE CALLBACKS
// ============================================================================
class PairTokenCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    String value = characteristic->getValue();
    if (value.length() == 0) return;
    g_pairTokenFromApp = value;
    g_pairTokenReady = true;
    setPairStatus("token_received");
  }
};

class AudioControlCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    String value = characteristic->getValue();
    value.trim();
    value.toLowerCase();
    if (value.length() == 0) return;

    if (value == "start") {
      startLiveRecording();
    } else if (value == "stop") {
      g_stopRecordingRequested = true;
    }
  }
};

// ============================================================================
// BLE SETUP
// ============================================================================
void setupBle() {
  BLEDevice::init(DEVICE_BLE_NAME);
  g_bleServer = BLEDevice::createServer();
  g_pairService = g_bleServer->createService(PAIR_SERVICE_UUID);

  g_deviceInfoChar = g_pairService->createCharacteristic(
      DEVICE_INFO_CHAR_UUID, BLECharacteristic::PROPERTY_READ);
  g_pairNonceChar = g_pairService->createCharacteristic(
      PAIR_NONCE_CHAR_UUID, BLECharacteristic::PROPERTY_READ);
  g_pairTokenChar = g_pairService->createCharacteristic(
      PAIR_TOKEN_CHAR_UUID, BLECharacteristic::PROPERTY_WRITE);
  g_pairTokenChar->setCallbacks(new PairTokenCallbacks());

  g_pairStatusChar = g_pairService->createCharacteristic(
      PAIR_STATUS_CHAR_UUID,
      BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ);
  g_pairStatusChar->addDescriptor(new BLE2902());

  g_audioControlChar = g_pairService->createCharacteristic(
      AUDIO_CONTROL_CHAR_UUID, BLECharacteristic::PROPERTY_WRITE);
  g_audioControlChar->setCallbacks(new AudioControlCallbacks());

  g_audioDataChar = g_pairService->createCharacteristic(
      AUDIO_DATA_CHAR_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  g_audioDataChar->addDescriptor(new BLE2902());

  g_audioStateChar = g_pairService->createCharacteristic(
      AUDIO_STATE_CHAR_UUID,
      BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ);
  g_audioStateChar->addDescriptor(new BLE2902());

  StaticJsonDocument<192> infoDoc;
  infoDoc["device_code"] = DEVICE_CODE;
  infoDoc["fw_version"] = "2.0.0-ble-gateway";
  infoDoc["model"] = "ESP32-S3";
  String infoJson;
  serializeJson(infoDoc, infoJson);
  g_deviceInfoChar->setValue(infoJson.c_str());
  g_pairNonceChar->setValue("not_in_pair_mode");
  g_pairStatusChar->setValue("idle");
  g_audioStateChar->setValue("idle");

  g_pairService->start();
}

void startBleAdvertising() {
  BLEAdvertising *adv = BLEDevice::getAdvertising();
  if (!g_advConfigured) {
    adv->addServiceUUID(PAIR_SERVICE_UUID);
    adv->setScanResponse(true);
    g_advConfigured = true;
  }
  BLEDevice::startAdvertising();
  Serial.println("[BLE] advertising ON");
}

void stopBleAdvertising() {
  BLEDevice::stopAdvertising();
  Serial.println("[BLE] advertising OFF");
}

void enterPairingMode() {
  g_pairNonce = generateNonceHex(16);
  g_pairTokenFromApp = "";
  g_pairTokenReady = false;
  g_pairModeEndAt = millis() + PAIR_MODE_WINDOW_MS;
  g_isPairingMode = true;

  g_pairNonceChar->setValue(g_pairNonce.c_str());
  setPairStatus("pairing_mode");

  startBleAdvertising();

  Serial.printf("[PAIR] mode ON nonce=%s\n", g_pairNonce.c_str());
}

void exitPairingMode(const String &finalStatus) {
  g_isPairingMode = false;
  if (g_isPaired) {
    startBleAdvertising();
  } else {
    stopBleAdvertising();
  }
  setPairStatus(finalStatus);
  Serial.printf("[PAIR] mode OFF status=%s\n", finalStatus.c_str());
}

// ============================================================================
// AUDIO / I2S
// ============================================================================
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

bool readPcmExact(uint8_t *out, size_t expectedBytes) {
  size_t total = 0;
  int idleReads = 0;

  while (total < expectedBytes) {
    if (g_stopRecordingRequested) return false;

    int availableBytes = g_i2s.available();
    if (availableBytes <= 0) {
      idleReads++;
      if (idleReads >= 100) {
        Serial.println("[I2S] read timeout");
        return false;
      }
      vTaskDelay(pdMS_TO_TICKS(2));
      continue;
    }

    size_t wanted = static_cast<size_t>(availableBytes);
    size_t remaining = expectedBytes - total;
    if (wanted > remaining) wanted = remaining;

    size_t bytesRead = g_i2s.readBytes(reinterpret_cast<char *>(out + total), wanted);
    if (bytesRead == 0) {
      idleReads++;
      if (idleReads >= 40) {
        Serial.println("[I2S] read timeout");
        return false;
      }
      vTaskDelay(pdMS_TO_TICKS(1));
      continue;
    }

    idleReads = 0;
    total += bytesRead;
  }
  return true;
}

void processAudioInPlace(uint8_t *pcmBytes, size_t byteLen) {
  if (!pcmBytes || byteLen < 2) return;

  int16_t *samples = reinterpret_cast<int16_t *>(pcmBytes);
  size_t sampleCount = byteLen / sizeof(int16_t);
  for (size_t i = 0; i < sampleCount; ++i) {
    float x = static_cast<float>(samples[i]);
#if AUDIO_ENABLE_DC_BLOCK
    float y = x - g_dcPrevX + (AUDIO_DC_BLOCK_R * g_dcPrevY);
    g_dcPrevX = x;
    g_dcPrevY = y;
    x = y;
#endif
    float v = x * AUDIO_GAIN;
    if (v > 32767.0f) v = 32767.0f;
    if (v < -32768.0f) v = -32768.0f;
    samples[i] = static_cast<int16_t>(v);
  }
}

// ============================================================================
// RECORDING TASK
// ============================================================================
void recordingTask(void *param) {
  const size_t packetWithHeader = BLE_AUDIO_PACKET_PCM_BYTES + 4;
  uint8_t *packet = static_cast<uint8_t *>(malloc(packetWithHeader));
  if (!packet) {
    Serial.println("[REC_TASK] alloc failed");
    vTaskDelete(nullptr);
    return;
  }

  uint8_t *pcm = packet + 4;
  Serial.printf("[REC_TASK] running core=%d\n", xPortGetCoreID());

  while (true) {
    if (!g_recordingActive) {
      vTaskDelay(pdMS_TO_TICKS(20));
      continue;
    }

    if (!readPcmExact(pcm, BLE_AUDIO_PACKET_PCM_BYTES)) {
      if (g_stopRecordingRequested) {
        g_stopRecordingRequested = false;
        stopLiveRecording(false);
      } else {
        stopLiveRecording(true);
      }
      continue;
    }

    if (g_stopRecordingRequested) {
      g_stopRecordingRequested = false;
      stopLiveRecording(false);
      continue;
    }

    processAudioInPlace(pcm, BLE_AUDIO_PACKET_PCM_BYTES);

    uint32_t seq = g_blePacketSeq;
    packet[0] = static_cast<uint8_t>((seq >> 24) & 0xFF);
    packet[1] = static_cast<uint8_t>((seq >> 16) & 0xFF);
    packet[2] = static_cast<uint8_t>((seq >> 8) & 0xFF);
    packet[3] = static_cast<uint8_t>(seq & 0xFF);

    if (g_audioDataChar) {
      g_audioDataChar->setValue(packet, packetWithHeader);
      g_audioDataChar->notify();
    }

    g_blePacketSeq++;
    if ((g_blePacketSeq % 100) == 0) {
      Serial.printf("[REC] BLE packets=%lu\n", static_cast<unsigned long>(g_blePacketSeq));
    }
  }
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

  g_stopRecordingRequested = false;
  g_blePacketSeq = 0;
  g_dcPrevX = 0.0f;
  g_dcPrevY = 0.0f;
  g_recordingActive = true;
  setAudioState("capturing");
  Serial.println("[REC] BLE live audio started");
  return true;
}

void stopLiveRecording(bool dueToError) {
  if (!g_recordingActive) return;
  g_recordingActive = false;
  if (dueToError) setAudioState("error");
  else setAudioState("idle");
  Serial.printf("[REC] BLE live audio stopped packets=%lu\n", static_cast<unsigned long>(g_blePacketSeq));
  g_blePacketSeq = 0;
}

// ============================================================================
// PAIRING STATE HANDLERS
// ============================================================================
void handlePairButton() {
#if PAIR_BUTTON_PIN < 0
  return;
#endif
  bool down = digitalRead(PAIR_BUTTON_PIN) == LOW;
  if (down && !g_buttonWasDown) g_buttonPressedAt = millis();
  if (!down && g_buttonWasDown) g_buttonPressedAt = 0;
  g_buttonWasDown = down;
  if (down && g_buttonPressedAt > 0 && (millis() - g_buttonPressedAt) >= LONG_PRESS_MS && !g_isPairingMode) {
    enterPairingMode();
    g_buttonPressedAt = 0;
  }
}

void handlePairingState() {
  if (!g_isPairingMode) return;
  if (millis() > g_pairModeEndAt) {
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

// ============================================================================
// SERIAL COMMANDS
// ============================================================================
void printSerialHelp() {
  Serial.println("\n=== SecondMind ESP32 Commands ===");
  Serial.println("p : enter pairing mode");
  Serial.println("s : start BLE live audio (phone gateway)");
  Serial.println("t : stop BLE live audio");
  Serial.println("u : re-auth device");
  Serial.println("x : clear paired flag");
  Serial.println("h : show this help");
  Serial.println("=================================\n");
}

void handleSerialCommands() {
  while (Serial.available()) {
    char c = static_cast<char>(Serial.read());
    switch (c) {
      case 'p':
        enterPairingMode();
        break;
      case 's':
        startLiveRecording();
        break;
      case 't':
        g_stopRecordingRequested = true;
        break;
      case 'u':
        authDevice();
        break;
      case 'x':
        g_isPaired = false;
        g_prefs.putBool("paired", false);
        Serial.println("[PAIR] paired flag cleared");
        break;
      case 'h':
        printSerialHelp();
        break;
      default:
        break;
    }
  }
}

// ============================================================================
// SETUP / LOOP
// ============================================================================
void setup() {
  Serial.begin(115200);
  delay(200);

#if PAIR_BUTTON_PIN >= 0
  pinMode(PAIR_BUTTON_PIN, INPUT_PULLUP);
#endif

  g_prefs.begin("secondmind", false);
  g_isPaired = g_prefs.getBool("paired", false);

  setupBle();
  initI2S();

  if (g_isPaired) {
    Serial.println("[BOOT] Device already paired.");
    setPairStatus("idle");
    startBleAdvertising();
  } else {
    Serial.println("[BOOT] Device not paired.");
#if TEST_MODE_AUTO_PAIR_ON_BOOT
    enterPairingMode();
#endif
  }

  xTaskCreatePinnedToCore(
      recordingTask,
      "rec_task",
      8192,
      nullptr,
      5,
      &g_recTaskHandle,
      1);

  printSerialHelp();
}

void loop() {
  handleSerialCommands();
  handlePairButton();
  handlePairingState();
  delay(10);
}
