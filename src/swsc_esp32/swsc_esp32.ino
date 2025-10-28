/*****************************************************
 * SMART WELLNESS & STUDY COMPANION (SWSC) – ESP32
 * ---------------------------------------------------
 * ESP32 + DHT11 + LDR + OLED SSD1306 + RGB LED + Buzzer
 * MQTT (HiveMQ) — sinkron dengan Flask backend (controller.py)
 *
 * Fitur utama:
 * - Subscribe awal ke swsc/config/#, swsc/control/#, swsc/alert/#
 * - Terima retained config → OLED tidak lagi "Waiting for Config"
 * - Handler alert break & water (START/END, START:id/STOP:id, PING)
 * - Publish data sensor ke swsc/data/* (±2 detik)
 * - Publish status sistem ke swsc/status/system
 * - Reconnect WiFi & MQTT dengan re-subscribe otomatis
 *****************************************************/

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>

/* ================== NETWORK CONFIG ================== */
const char* WIFI_SSID     = "AworaworG";     // ← ganti jika perlu
const char* WIFI_PASS     = "HRRZYA22";      // ← ganti jika perlu
const char* MQTT_SERVER   = "broker.hivemq.com";
const int   MQTT_PORT     = 1883;

/* ============== TOPICS (HARUS SAMA DGN BACKEND) ============== */
const char* TPC_CONFIG_DURATION       = "swsc/config/duration";
const char* TPC_CONFIG_BREAK_INTERVAL = "swsc/config/break_interval";
const char* TPC_CONFIG_BREAK_LENGTH   = "swsc/config/break_length";
const char* TPC_CONFIG_WATER_REM      = "swsc/config/water_reminder";

const char* TPC_CONTROL_START         = "swsc/control/start";
const char* TPC_CONTROL_STOP          = "swsc/control/stop";
const char* TPC_CONTROL_RESET         = "swsc/control/reset";

const char* TPC_ALERT_BREAK           = "swsc/alert/break";  // "START" / "END"
const char* TPC_ALERT_WATER           = "swsc/alert/water";  // "START:id" / "STOP:id" / "PING:ids"

const char* TPC_DATA_TEMP             = "swsc/data/temperature";
const char* TPC_DATA_HUM              = "swsc/data/humidity";
const char* TPC_DATA_LIGHT            = "swsc/data/light";

const char* TPC_STATUS_SYSTEM         = "swsc/status/system";

/* ================== HARDWARE PINS ================== */
#define DHT_PIN       4
#define DHT_TYPE      DHT11
#define LDR_PIN       34           // ADC1_CH6
#define BUZZER_PIN    26           // ubah ke 18 jika rangkaianmu pakai 18
#define LED_RED       19
#define LED_GREEN     23
#define LED_BLUE      25

/* ================== OLED CONFIG ================== */
#define OLED_WIDTH    128
#define OLED_HEIGHT   64
#define OLED_ADDRESS  0x3C

/* ================== OBJECTS ================== */
WiFiClient        espClient;
PubSubClient      mqtt(espClient);
Adafruit_SSD1306  display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);
DHT               dht(DHT_PIN, DHT_TYPE);

/* ================== APP STATE ================== */
// Konfigurasi sesi (datang dari retained config)
volatile int  cfg_duration_min       = 0;    // total durasi
volatile int  cfg_break_interval_min = 0;    // interval antar break
volatile int  cfg_break_length_min   = 0;    // lama break
volatile bool cfg_water_on           = false;

volatile bool cfg_received_any       = false;   // minimal satu config diterima
volatile bool cfg_ready              = false;   // semua config inti diterima

// Status runtime
volatile bool session_running        = false;   // START/STOP oleh backend
volatile bool in_break               = false;   // break phase indikator
volatile bool session_stopped        = false;

// Water alarms (ID yang aktif → buzzer periodik sampai STOP/ack)
static const int MAX_WATER_ALARMS = 32;   // aman untuk milestone banyak
bool water_active[MAX_WATER_ALARMS] = { false };

// Timing
unsigned long lastSensorMs   = 0;
unsigned long lastBuzzMs     = 0;
unsigned long buzzUntilMs    = 0;

// Buzzer cadence
const uint16_t BUZZ_SHORT_MS = 120;
const uint16_t BUZZ_GAP_MS   = 100;

// Sensor sampling interval
const uint32_t SENSOR_INTERVAL_MS = 2000; // 2 detik

/* ================== UTILS ================== */
void ledColor(uint8_t r, uint8_t g, uint8_t b) {
  digitalWrite(LED_RED,   r ? HIGH : LOW);
  digitalWrite(LED_GREEN, g ? HIGH : LOW);
  digitalWrite(LED_BLUE,  b ? HIGH : LOW);
}

void buzzerOn() {
  digitalWrite(BUZZER_PIN, HIGH);
}
void buzzerOff() {
  digitalWrite(BUZZER_PIN, LOW);
}

void beepOnce(uint16_t ms) {
  buzzerOn();
  delay(ms);
  buzzerOff();
}

void buzzPattern_BreakStart() {
  // Tiga beep pendek: --- --- ---
  for (int i = 0; i < 3; ++i) {
    beepOnce(BUZZ_SHORT_MS);
    delay(BUZZ_GAP_MS);
  }
}
void buzzPattern_BreakEnd() {
  // Dua beep panjang: ===== =====
  buzzerOn(); delay(300); buzzerOff(); delay(150);
  buzzerOn(); delay(300); buzzerOff();
}

void clearDisplay() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
}

void drawCentered(const String& s, int16_t y, uint8_t size = 1) {
  display.setTextSize(size);
  int16_t x1, y1; uint16_t w, h;
  display.getTextBounds(s, 0, 0, &x1, &y1, &w, &h);
  int16_t x = (OLED_WIDTH - (int)w)/2;
  display.setCursor(x < 0 ? 0 : x, y);
  display.print(s);
}

void showSplash() {
  clearDisplay();
  drawCentered("SWSC", 10, 2);
  drawCentered("Smart Wellness", 30, 1);
  drawCentered("& Study Companion", 42, 1);
  display.display();
}

void showWaiting() {
  clearDisplay();
  drawCentered("Waiting for", 18, 1);
  drawCentered("Configuration", 30, 1);
  drawCentered("...", 44, 1);
  display.display();
}

void showConfigured() {
  clearDisplay();
  drawCentered("Configured", 10, 2);
  display.setTextSize(1);
  display.setCursor(2, 34);
  display.print("Duration : "); display.print(cfg_duration_min); display.println(" min");
  display.setCursor(2, 44);
  display.print("Break/Int: "); display.print(cfg_break_interval_min); display.println(" min");
  display.setCursor(2, 54);
  display.print("Break Len: "); display.print(cfg_break_length_min); display.println(" min");
  display.display();
}

void showRunning() {
  clearDisplay();
  drawCentered(in_break ? "BREAK" : "SESSION", 0, 2);
  display.setTextSize(1);
  display.setCursor(2, 26);
  display.print("WiFi: "); display.println(WiFi.isConnected() ? "OK" : "OFF");
  display.setCursor(2, 36);
  display.print("Dur (min): "); display.println(cfg_duration_min);
  display.setCursor(2, 46);
  display.print("Int/Len : "); display.print(cfg_break_interval_min);
  display.print("/"); display.println(cfg_break_length_min);
  display.setCursor(2, 56);
  display.print("Water  : "); display.println(cfg_water_on ? "ON" : "OFF");
  display.display();
}

void showStopped() {
  clearDisplay();
  drawCentered("STOPPED", 20, 2);
  display.display();
}

void showEnv(float t, float h, int light) {
  // small overlay summary (called after main screen or as tick)
  clearDisplay();
  display.setTextSize(1);
  display.setCursor(2, 0);
  display.print("Status: ");
  display.println(session_running ? (in_break ? "Break" : "Running") : (cfg_ready ? "Ready" : "Waiting"));

  display.setCursor(2, 14);
  display.print("Temp: "); display.print(isnan(t) ? -1 : t); display.println(" C");
  display.setCursor(2, 24);
  display.print("Hum : "); display.print(isnan(h) ? -1 : h); display.println(" %");
  display.setCursor(2, 34);
  display.print("Light: "); display.print(light); display.println(" lux");

  display.setCursor(2, 48);
  display.print("WiFi: "); display.print(WiFi.isConnected() ? "OK" : "OFF");
  display.setCursor(64, 48);
  display.print("MQTT: "); display.print(mqtt.connected() ? "OK" : "OFF");
  display.display();
}

/* ================== MQTT HELPERS ================== */
void publishStatus(const char* msg) {
  mqtt.publish(TPC_STATUS_SYSTEM, msg, true); // retain status
}

/* ================== WIFI & MQTT ================== */
void setupWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("[WiFi] Connecting");
  uint8_t dots = 0;
  while (WiFi.status() != WL_CONNECTED) {
    Serial.print(".");
    delay(350);
    if (++dots % 20 == 0) Serial.println();
  }
  Serial.println();
  Serial.print("[WiFi] Connected, IP: "); Serial.println(WiFi.localIP());
}

String makeClientId() {
  String id = "SWSC_ESP32_";
  id += String((uint32_t)ESP.getEfuseMac(), HEX);
  return id;
}

void subscribeAll() {
  mqtt.subscribe("swsc/config/#");
  mqtt.subscribe("swsc/control/#");
  mqtt.subscribe("swsc/alert/#");
  mqtt.subscribe("swsc/status/#");
  mqtt.subscribe("swsc/data/#");
  Serial.println("[MQTT] Subscribed to: config/control/alert/status/data");
}

void connectMQTT() {
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  Serial.print("[MQTT] Connecting to broker");
  while (!mqtt.connected()) {
    Serial.print(".");
    if (mqtt.connect(makeClientId().c_str())) break;
    delay(800);
  }
  Serial.println();
  Serial.println("[MQTT] Connected");
  subscribeAll();

  // beri waktu broker mengirim retained msgs
  delay(500);

  // Publish status awal
  if (!cfg_ready) publishStatus("Waiting for Config");
  else            publishStatus(session_running ? (in_break ? "Break" : "Running") : "Ready");
}

/* ================== CONFIG PARSER ================== */
void parseConfig(const char* topic, const String& payload) {
  if (strcmp(topic, TPC_CONFIG_DURATION) == 0) {
    cfg_duration_min = payload.toInt();
    cfg_received_any = true;
  } else if (strcmp(topic, TPC_CONFIG_BREAK_INTERVAL) == 0) {
    cfg_break_interval_min = payload.toInt();
    cfg_received_any = true;
  } else if (strcmp(topic, TPC_CONFIG_BREAK_LENGTH) == 0) {
    cfg_break_length_min = payload.toInt();
    cfg_received_any = true;
  } else if (strcmp(topic, TPC_CONFIG_WATER_REM) == 0) {
    String v = payload; v.toLowerCase();
    cfg_water_on = (v == "on" || v == "true" || v == "1");
    cfg_received_any = true;
  }
  // Siap jika semua inti masuk (durasi + interval + length)
  cfg_ready = (cfg_duration_min > 0 && cfg_break_interval_min >= 0 && cfg_break_length_min >= 0);
  if (cfg_ready && !session_running) {
    ledColor(0, 255, 0); // Green = configured
    showConfigured();
    publishStatus("Ready");
  }
}

/* ================== ALERT HANDLERS ================== */
void resetWaterAlarms() {
  for (int i = 0; i < MAX_WATER_ALARMS; ++i) water_active[i] = false;
}

void handleAlertBreak(const String& p) {
  if (p == "START") {
    in_break = true;
    ledColor(255, 255, 0); // Yellow
    buzzPattern_BreakStart();
    showRunning();
    publishStatus("Break");
  } else if (p == "END") {
    in_break = false;
    ledColor(0, 255, 0); // Green back to running
    buzzPattern_BreakEnd();
    showRunning();
    publishStatus("Running");
  }
}

void handleAlertWater(const String& p) {
  // "START:id" / "STOP:id" / "PING:ids"
  if (p.startsWith("START:")) {
    int id = p.substring(6).toInt();
    if (id >= 0 && id < MAX_WATER_ALARMS) {
      water_active[id] = true;
      // bunyikan beep pendek saat mulai
      beepOnce(BUZZ_SHORT_MS);
    }
  } else if (p.startsWith("STOP:")) {
    int id = p.substring(5).toInt();
    if (id >= 0 && id < MAX_WATER_ALARMS) {
      water_active[id] = false;
      // diamkan buzzer
      buzzerOff();
    }
  } else if (p.startsWith("PING:")) {
    // PING:0,1,2 — cukup beep ringan, jangan blocking lama
    // Jika ada water_active TRUE, akan ada beep periodik di loop
    beepOnce(80);
  }
}

/* ================== CONTROL HANDLERS ================== */
void handleControlStart() {
  if (!cfg_ready) {
    // belum ada config lengkap
    publishStatus("Waiting for Config");
    showWaiting();
    ledColor(0, 0, 255); // Blue
    return;
  }
  session_running = true;
  session_stopped = false;
  in_break = false;
  resetWaterAlarms();
  ledColor(0, 255, 0); // Green
  showRunning();
  publishStatus("Running");
}

void handleControlStop() {
  session_running = false;
  session_stopped = true;
  in_break = false;
  resetWaterAlarms();
  buzzerOff();

  beepOnce(400);

  ledColor(255, 0, 0); // Red
  showStopped();
  publishStatus("Stopped");
}

void handleControlReset() {
  session_running = false;
  session_stopped = false;
  in_break = false;
  resetWaterAlarms();
  buzzerOff();
  // tetap simpan config yang sudah diterima (cfg_* tidak di-nol-kan)
  if (cfg_ready) {
    ledColor(0, 255, 0);
    showConfigured();
    publishStatus("Ready");
  } else {
    ledColor(0, 0, 255);
    showWaiting();
    publishStatus("Waiting for Config");
  }
}

/* ================== MQTT CALLBACK ================== */
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg;
  msg.reserve(length);
  for (unsigned int i = 0; i < length; ++i) msg += (char)payload[i];

  // Debug
  Serial.print("[MQTT] "); Serial.print(topic); Serial.print(" = "); Serial.println(msg);

  // CONFIG
  if (strncmp(topic, "swsc/config/", 12) == 0) {
    parseConfig(topic, msg);
    return;
  }

  // CONTROL
  if (strcmp(topic, TPC_CONTROL_START) == 0) {
    handleControlStart(); return;
  }
  if (strcmp(topic, TPC_CONTROL_STOP) == 0) {
    handleControlStop(); return;
  }
  if (strcmp(topic, TPC_CONTROL_RESET) == 0) {
    handleControlReset(); return;
  }

  // ALERT
  if (strcmp(topic, TPC_ALERT_BREAK) == 0) {
    handleAlertBreak(msg); return;
  }
  if (strcmp(topic, TPC_ALERT_WATER) == 0) {
    handleAlertWater(msg); return;
  }
}

/* ================== SENSOR & PUBLISH ================== */
int readLightLux() {
  // ADC 0..4095 → mapping sederhana ke "lux" pseudo (untuk tampilan)
  int raw = analogRead(LDR_PIN);
  // Normalisasi kasar (opsional sesuaikan dengan rangkaian):
  // lux ~ (4095 - raw) * scale
  int lux = (4095 - raw) / 2;  // angka "visual", bukan lux absolut
  if (lux < 0)   lux = 0;
  if (lux > 5000) lux = 5000;
  return lux;
}

void sampleAndPublishSensors() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  int   l = readLightLux();

  // publish string aman (jika NaN, kirim "-")
  char buf[32];

  if (isnan(t)) mqtt.publish(TPC_DATA_TEMP, "-", false);
  else {
    dtostrf(t, 0, 1, buf);
    mqtt.publish(TPC_DATA_TEMP, buf, false);
  }

  if (isnan(h)) mqtt.publish(TPC_DATA_HUM, "-", false);
  else {
    dtostrf(h, 0, 1, buf);
    mqtt.publish(TPC_DATA_HUM, buf, false);
  }

  snprintf(buf, sizeof(buf), "%d", l);
  mqtt.publish(TPC_DATA_LIGHT, buf, false);

  // Update OLED ringkas agar user lihat perubahan
  showEnv(t, h, l);
}

/* ================== SETUP & LOOP ================== */
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n\n=== SWSC - Smart Wellness & Study Companion ===");
  Serial.println("Version: 2.2 (Sync, Retain, Robust)");
  Serial.println("===============================================\n");

  // Pins
  pinMode(BUZZER_PIN, OUTPUT); digitalWrite(BUZZER_PIN, LOW);
  pinMode(LED_RED, OUTPUT);    digitalWrite(LED_RED, LOW);
  pinMode(LED_GREEN, OUTPUT);  digitalWrite(LED_GREEN, LOW);
  pinMode(LED_BLUE, OUTPUT);   digitalWrite(LED_BLUE, LOW);
  pinMode(LDR_PIN, INPUT);

  // Sensors
  dht.begin();
  Serial.println("[INIT] DHT11 initialized");

  // OLED
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS)) {
    Serial.println("[ERROR] OLED init failed!");
    while (1) { delay(1000); }
  }
  Serial.println("[INIT] OLED initialized");

  showSplash();
  delay(1500);

  // Network
  setupWiFi();

  // MQTT
  mqtt.setCallback(mqttCallback);
  connectMQTT();

  // Setelah subscribe aktif, tampilkan waiting/ready
  if (!cfg_ready) {
    showWaiting();
    ledColor(0, 0, 255);           // Blue
    publishStatus("Waiting for Config");
  } else {
    showConfigured();
    ledColor(0, 255, 0);           // Green
    publishStatus("Ready");
  }

  Serial.println("\n[READY] System ready.\n");
}

void loop() {
  // Reconnect WiFi
  if (WiFi.status() != WL_CONNECTED) {
    ledColor(255, 0, 0); // Red
    WiFi.reconnect();
    delay(500);
    return;
  }

  // Reconnect MQTT
  if (!mqtt.connected()) {
    connectMQTT();
  }
  mqtt.loop();

  // Sensor sampling & publish tiap ±2 detik
  unsigned long now = millis();
  if (now - lastSensorMs >= SENSOR_INTERVAL_MS) {
    lastSensorMs = now;
    if (!session_stopped) { // <-- TAMBAHKAN KONDISI INI
      sampleAndPublishSensors();
    }
  }

  // Buzzer water alarms: jika ada alarm aktif, bunyikan periodik non-blocking
  bool anyWater = false;
  for (int i = 0; i < MAX_WATER_ALARMS; ++i) {
    if (water_active[i]) { anyWater = true; break; }
  }
  if (anyWater) {
    // bunyikan beep pendek setiap ~2.5 detik
    if (now - lastBuzzMs >= 2500) {
      lastBuzzMs = now;
      beepOnce(100);
    }
  } else {
    // pastikan buzzer mati bila tidak ada alarm
    buzzerOff();
  }

  // Status LED ringkas berdasarkan state
  if (!cfg_ready) {
    ledColor(0, 0, 255); // Blue
  } else if (session_stopped) { // <-- TAMBAHKAN BLOK INI
    ledColor(255, 0, 0); // Red
  } else if (!session_running) {
    ledColor(0, 255, 0); // Green (siap)
  } else {
    // running/break
    if (in_break) ledColor(255, 255, 0); // Yellow saat break
    else          ledColor(0, 255, 0); // Green saat running
  }
}