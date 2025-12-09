// Includes
#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>

// WiFi & MQTT Settings
const char* WIFI_SSID     = "Aworawor";     
const char* WIFI_PASS     = "HRRZYA22";     
const char* MQTT_SERVER   = "broker.hivemq.com";
const int   MQTT_PORT     = 1883;

// MQTT Topics
const char* TPC_CONFIG_DURATION       = "swsc/config/duration";
const char* TPC_CONFIG_BREAK_INTERVAL = "swsc/config/break_interval";
const char* TPC_CONFIG_BREAK_LENGTH   = "swsc/config/break_length";
const char* TPC_CONFIG_WATER_REM      = "swsc/config/water_reminder";

const char* TPC_CONTROL_START         = "swsc/control/start";
const char* TPC_CONTROL_STOP          = "swsc/control/stop";
const char* TPC_CONTROL_RESET         = "swsc/control/reset";

const char* TPC_ALERT_BREAK           = "swsc/alert/break"; 
const char* TPC_ALERT_WATER           = "swsc/alert/water";

const char* TPC_DATA_TEMP             = "swsc/data/temperature";
const char* TPC_DATA_HUM              = "swsc/data/humidity";
const char* TPC_DATA_LIGHT            = "swsc/data/light";

const char* TPC_STATUS_SYSTEM         = "swsc/status/system";

// Pin Definitions
#define DHT_PIN       4
#define DHT_TYPE      DHT11
#define LDR_PIN       34           
#define BUZZER_PIN    26
#define LED_RED       19
#define LED_GREEN     23
#define LED_BLUE      25
#define BUZZER_FREQ   1500

// OLED Definitions
#define OLED_WIDTH    128
#define OLED_HEIGHT   64
#define OLED_ADDRESS  0x3C

// Objects
WiFiClient        espClient;
PubSubClient      mqtt(espClient);
Adafruit_SSD1306  display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);
DHT               dht(DHT_PIN, DHT_TYPE);

// Configuration parameters
volatile int  cfg_duration_min       = 0;     // total durasi
volatile int  cfg_break_interval_min = 0;     // interval antar break
volatile int  cfg_break_length_min   = 0;     // lama break
volatile bool cfg_water_on           = false; 
volatile bool cfg_received_any       = false; 
volatile bool cfg_ready              = false; 
volatile bool led_state              = false;

// Status runtime
volatile bool session_running        = false;
volatile bool in_break               = false;
volatile bool session_stopped        = false;

// Water reminder alarms
static const int MAX_WATER_ALARMS = 32; 
bool water_active[MAX_WATER_ALARMS] = { false };

// Timing
unsigned long lastSensorMs   = 0;
unsigned long lastBuzzMs     = 0;
unsigned long lastBlinkMs    = 0;
unsigned long buzzUntilMs    = 0;

// Buzzer patterns
const uint16_t BUZZ_SHORT_MS = 120;
const uint16_t BUZZ_GAP_MS   = 100;

// Sensor sampling interval
const uint32_t SENSOR_INTERVAL_MS = 2000;

// Helpers
void ledColor(uint8_t r, uint8_t g, uint8_t b) {
  digitalWrite(LED_RED,   r ? HIGH : LOW);
  digitalWrite(LED_GREEN, g ? HIGH : LOW);
  digitalWrite(LED_BLUE,  b ? HIGH : LOW);
}

void buzzerOn() {
  tone(BUZZER_PIN, BUZZER_FREQ);
}

void buzzerOff() {
  noTone(BUZZER_PIN);
}

void beepOnce(uint16_t ms) {
  buzzerOn();
  delay(ms);
  buzzerOff();
}

void buzzPattern_BreakStart() {
  for (int i = 0; i < 3; ++i) {
    beepOnce(BUZZ_SHORT_MS);
    delay(BUZZ_GAP_MS);
  }
}

void buzzPattern_BreakEnd() {
  buzzerOn(); delay(300); buzzerOff(); delay(150);
  buzzerOn(); delay(300); buzzerOff();
}

void buzzPattern_TwoBeeps() {
  for (int i = 0; i < 2; ++i) {
    beepOnce(BUZZ_SHORT_MS);
    delay(BUZZ_GAP_MS);
  }
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
  display.print("Light: "); display.println(light == 0 ? "Gelap" : "Terang");

  display.setCursor(2, 48);
  display.print("WiFi: "); display.print(WiFi.isConnected() ? "OK" : "OFF");
  display.setCursor(64, 48);
  display.print("MQTT: "); display.print(mqtt.connected() ? "OK" : "OFF");
  display.display();
}

void publishStatus(const char* msg) {
  mqtt.publish(TPC_STATUS_SYSTEM, msg, true);
}

// Setup WiFi & MQTT
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
  delay(500);

  if (!cfg_ready) publishStatus("Waiting for Config");
  else            publishStatus(session_running ? (in_break ? "Break" : "Running") : "Ready");
}

// Config parser
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
  cfg_ready = (cfg_duration_min > 0 && cfg_break_interval_min >= 0 && cfg_break_length_min >= 0);
  if (cfg_ready && !session_running) {
    ledColor(0, 255, 0);
    showConfigured();
    publishStatus("Ready");
  }
}

// Alert Handlers
void resetWaterAlarms() {
  for (int i = 0; i < MAX_WATER_ALARMS; ++i) water_active[i] = false;
}

void handleAlertBreak(const String& p) {
  if (p == "START") {
    in_break = true;
    buzzPattern_TwoBeeps();
    showRunning();
    publishStatus("Break");
  } else if (p == "END") {
    in_break = false;
    buzzPattern_BreakEnd();
    showRunning();
    publishStatus("Running");
  }
}

void handleAlertWater(const String& p) {
  if (p.startsWith("START:")) {
    int id = p.substring(6).toInt();
    if (id >= 0 && id < MAX_WATER_ALARMS) {
      water_active[id] = true;
      beepOnce(BUZZ_SHORT_MS);
    }
  } else if (p.startsWith("STOP:")) {
    int id = p.substring(5).toInt();
    if (id >= 0 && id < MAX_WATER_ALARMS) {
      water_active[id] = false;
      buzzerOff();
    }
  } else if (p.startsWith("PING:")) {
    beepOnce(80);
  }
}

// Control Handlers
void handleControlStart() {
  if (!cfg_ready) {
    publishStatus("Waiting for Config");
    showWaiting();
    ledColor(0, 0, 255);
    return;
  }

  session_running = true;
  session_stopped = false;
  in_break = false;
  resetWaterAlarms();
  buzzPattern_TwoBeeps();
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
  showStopped();
  publishStatus("Stopped");
}

void handleControlReset() {
  session_running = false;
  session_stopped = false;
  in_break = false;
  resetWaterAlarms();
  buzzerOff();
  if (cfg_ready) {
    showConfigured();
    publishStatus("Ready");
  } else {
    showWaiting();
    publishStatus("Waiting for Config");
  }
}

// MQTT Callback
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg;
  msg.reserve(length);
  for (unsigned int i = 0; i < length; ++i) msg += (char)payload[i];

  Serial.print("[MQTT] "); Serial.print(topic); Serial.print(" = "); Serial.println(msg);

  if (strncmp(topic, "swsc/config/", 12) == 0) {
    parseConfig(topic, msg);
    return;
  }
  if (strcmp(topic, TPC_CONTROL_START) == 0) {
    handleControlStart(); return;
  }
  if (strcmp(topic, TPC_CONTROL_STOP) == 0) {
    handleControlStop(); return;
  }
  if (strcmp(topic, TPC_CONTROL_RESET) == 0) {
    handleControlReset(); return;
  }
  if (strcmp(topic, TPC_ALERT_BREAK) == 0) {
    handleAlertBreak(msg); return;
  }
  if (strcmp(topic, TPC_ALERT_WATER) == 0) {
    handleAlertWater(msg); return;
  }
}

// Sensor Reading & Publishing
int readLightLux() {
  int state = digitalRead(LDR_PIN);

  if (state == LOW) {
    return 1; 
  } else {
    return 0;
  }
}

void sampleAndPublishSensors() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  int   l = readLightLux();

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

  showEnv(t, h, l);
}

// Main Setup & Loop
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n\n=== SWSC - Smart Wellness & Study Companion ===");
  Serial.println("===============================================\n");

  pinMode(BUZZER_PIN, OUTPUT); digitalWrite(BUZZER_PIN, LOW);
  pinMode(LED_RED, OUTPUT);    digitalWrite(LED_RED, LOW);
  pinMode(LED_GREEN, OUTPUT);  digitalWrite(LED_GREEN, LOW);
  pinMode(LED_BLUE, OUTPUT);   digitalWrite(LED_BLUE, LOW);
  pinMode(LDR_PIN, INPUT);

  dht.begin();
  Serial.println("[INIT] DHT11 initialized");

  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS)) {
    Serial.println("[ERROR] OLED init failed!");
    while (1) { delay(1000); }
  }
  Serial.println("[INIT] OLED initialized");

  showSplash();
  delay(1500);

  setupWiFi();
  mqtt.setCallback(mqttCallback);
  connectMQTT();

  if (!cfg_ready) {
    showWaiting();
    publishStatus("Waiting for Config");
  } else {
    showConfigured();
    publishStatus("Ready");
  }

  Serial.println("\n[READY] System ready.\n");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    delay(500);
    return;
  }

  if (!mqtt.connected()) {
    connectMQTT();
  }
  mqtt.loop();

  unsigned long now = millis();
  if (now - lastSensorMs >= SENSOR_INTERVAL_MS) {
    lastSensorMs = now;
    if (!session_stopped) {
      sampleAndPublishSensors();
    }
  }

  bool anyWater = false;
  for (int i = 0; i < MAX_WATER_ALARMS; ++i) {
    if (water_active[i]) { anyWater = true; break; }
  }

  if (anyWater && (now - lastBuzzMs >= 2500)) { 
    lastBuzzMs = now;
    beepOnce(BUZZ_SHORT_MS);
  }

  if (now - lastBlinkMs >= 500) {
    lastBlinkMs = now;
    led_state = !led_state;
  }

  if (anyWater || session_stopped || in_break) {
    if (led_state) ledColor(255, 0, 0);
    else           ledColor(0, 0, 0); 
  } else if (session_running) {
    if (led_state) ledColor(0, 255, 0);
    else           ledColor(0, 0, 0);
  } else if (cfg_ready) {
    if (led_state) ledColor(0, 0, 255); 
    else           ledColor(0, 0, 0); 
  } else {
    ledColor(0, 0, 255);
  }
}