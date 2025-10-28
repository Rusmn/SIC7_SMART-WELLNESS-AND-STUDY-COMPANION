/*
 * ═══════════════════════════════════════════════════════════════
 * SMART WELLNESS & STUDY COMPANION (SWSC) - FIXED VERSION
 * ───────────────────────────────────────────────────────────────
 * ESP32 dengan logic yang diperbaiki:
 * - Non-blocking reconnection
 * - Retained messages + QoS
 * - Proper MQTT loop handling
 * - Synchronized timing
 * ═══════════════════════════════════════════════════════════════
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>

// ============== NETWORK CONFIG ==============
const char* WIFI_SSID = "AworaworG";
const char* WIFI_PASSWORD = "HRRZYA22";
const char* MQTT_SERVER = "broker.hivemq.com";
const int MQTT_PORT = 1883;
const char* MQTT_CLIENT_ID = "SWSC_ESP32_"; // Will append MAC address

// ============== PIN DEFINITIONS ==============
#define DHT_PIN 4
#define LDR_PIN 34
#define BUZZER_PIN 26
#define LED_RED 19
#define LED_GREEN 23
#define LED_BLUE 25

#define DHTTYPE DHT11
#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_RESET -1
#define OLED_ADDRESS 0x3C

// ============== OBJECTS ==============
WiFiClient espClient;
PubSubClient mqtt(espClient);
DHT dht(DHT_PIN, DHTTYPE);
Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, OLED_RESET);

// ============== STATE VARIABLES ==============
struct SystemState {
  bool active = false;
  bool configReady = false;
  bool onBreak = false;
  bool waterReminderEnabled = true;
  
  int studyDuration = 0;      // minutes
  int breakInterval = 0;       // minutes
  int breakLength = 5;         // minutes
  int waterInterval = 30;      // minutes
  
  unsigned long startTime = 0;
  unsigned long intervalStartTime = 0;
  unsigned long lastWaterCheck = 0;
  
  float temperature = 0.0;
  float humidity = 0.0;
  int lightValue = 0;
  String environmentStatus = "Idle";
  String currentPhase = "Idle";
} state;

// ============== TIMING CONSTANTS ==============
const unsigned long DISPLAY_UPDATE_INTERVAL = 1000;    // 1 second
const unsigned long SENSOR_READ_INTERVAL = 5000;       // 5 seconds
const unsigned long MQTT_PUBLISH_INTERVAL = 5000;      // 5 seconds
const unsigned long MQTT_RECONNECT_INTERVAL = 5000;    // 5 seconds
const unsigned long LED_BLINK_INTERVAL = 500;          // 500ms

// ============== ENVIRONMENT THRESHOLDS ==============
const float TEMP_MIN = 20.0;
const float TEMP_MAX = 30.0;
const float HUM_MIN = 40.0;
const float HUM_MAX = 70.0;
const int LIGHT_MIN = 200;
const int LIGHT_MAX = 800;

// ============== TIMING TRACKERS ==============
unsigned long lastDisplayUpdate = 0;
unsigned long lastSensorRead = 0;
unsigned long lastMqttPublish = 0;
unsigned long lastMqttReconnect = 0;
unsigned long lastLedBlink = 0;
bool ledBlinkState = false;

// ============== BUZZER STATE ==============
bool buzzerActive = false;
unsigned long buzzerStartTime = 0;
int buzzerDuration = 0;

// ============== FUNCTION DECLARATIONS ==============
void setupWiFi();
void setupMQTT();
bool reconnectMQTT();
void mqttCallback(char* topic, byte* payload, unsigned int length);
void handleMQTTMessage(String topic, String payload);

void startSystem();
void stopSystem();
void resetSystem();

void readSensors();
void checkEnvironment();
void checkTimers();
void checkWaterReminder();

void triggerBreakAlert();
void triggerWaterAlert();
void stopWaterAlert();

void updateDisplay();
void showSplash();
void showWaiting();

void publishSensorData();
void publishStatus(String status);

void ledColor(int r, int g, int b);
void startBuzzer(int durationMs);
void updateBuzzer();

String getMACAddress();

// ════════════════════════════════════════════════════════════════
//                           SETUP
// ════════════════════════════════════════════════════════════════

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n\n=== SWSC - Smart Wellness & Study Companion ===");
  Serial.println("Version: 2.0 (Fixed Logic)");
  Serial.println("===============================================\n");

  // Initialize pins
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  pinMode(LDR_PIN, INPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // Initialize DHT sensor
  dht.begin();
  Serial.println("[INIT] DHT11 sensor initialized");

  // Initialize OLED display
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS)) {
    Serial.println("[ERROR] OLED initialization failed!");
    while (1); // Halt
  }
  Serial.println("[INIT] OLED display initialized");
  
  showSplash();
  delay(2000);

  // Connect to WiFi
  setupWiFi();

  // Setup MQTT
  setupMQTT();

  // Show waiting screen
  showWaiting();
  ledColor(0, 0, 255); // Blue = waiting for config

  Serial.println("\n[READY] System ready and waiting for configuration\n");
}

// ════════════════════════════════════════════════════════════════
//                         MAIN LOOP
// ════════════════════════════════════════════════════════════════

void loop() {
  unsigned long now = millis();

  // Handle MQTT connection
  if (!mqtt.connected()) {
    if (now - lastMqttReconnect >= MQTT_RECONNECT_INTERVAL) {
      lastMqttReconnect = now;
      if (reconnectMQTT()) {
        Serial.println("[MQTT] Reconnected successfully");
      }
    }
  } else {
    mqtt.loop(); // Process incoming messages
  }

  // Handle buzzer
  updateBuzzer();

  // If system not active, just blink LED and return
  if (!state.active) {
    if (now - lastLedBlink >= LED_BLINK_INTERVAL) {
      lastLedBlink = now;
      ledBlinkState = !ledBlinkState;
      ledColor(0, 0, ledBlinkState ? 255 : 0); // Blink blue
    }
    return;
  }

  // === ACTIVE MODE ===

  // Read sensors periodically
  if (now - lastSensorRead >= SENSOR_READ_INTERVAL) {
    lastSensorRead = now;
    readSensors();
    checkEnvironment();
  }

  // Check timers
  checkTimers();

  // Check water reminder
  if (state.waterReminderEnabled) {
    checkWaterReminder();
  }

  // Update display
  if (now - lastDisplayUpdate >= DISPLAY_UPDATE_INTERVAL) {
    lastDisplayUpdate = now;
    updateDisplay();
  }

  // Publish to MQTT
  if (now - lastMqttPublish >= MQTT_PUBLISH_INTERVAL) {
    lastMqttPublish = now;
    publishSensorData();
  }

  // Blink LED to show activity
  if (now - lastLedBlink >= LED_BLINK_INTERVAL) {
    lastLedBlink = now;
    ledBlinkState = !ledBlinkState;
    digitalWrite(LED_GREEN, ledBlinkState ? HIGH : LOW);
  }

  // Check if session completed
  unsigned long elapsedMinutes = (now - state.startTime) / 60000;
  if (state.studyDuration > 0 && elapsedMinutes >= state.studyDuration) {
    Serial.println("\n[SESSION] Study session completed!");
    publishStatus("completed");
    mqtt.publish("swsc/alert/finished", "Session completed! Great work!", true);
    stopSystem();
  }
}

// ════════════════════════════════════════════════════════════════
//                      WIFI & MQTT SETUP
// ════════════════════════════════════════════════════════════════

void setupWiFi() {
  Serial.print("[WIFI] Connecting to ");
  Serial.print(WIFI_SSID);
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WIFI] Connected!");
    Serial.print("[WIFI] IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.print("[WIFI] MAC Address: ");
    Serial.println(getMACAddress());
  } else {
    Serial.println("\n[ERROR] WiFi connection failed!");
    Serial.println("[ERROR] Please check SSID and password");
    while (1); // Halt
  }
}

void setupMQTT() {
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setKeepAlive(60);
  mqtt.setSocketTimeout(15);
  
  Serial.print("[MQTT] Broker: ");
  Serial.print(MQTT_SERVER);
  Serial.print(":");
  Serial.println(MQTT_PORT);
  
  // Initial connection attempt
  reconnectMQTT();
}

bool reconnectMQTT() {
  if (mqtt.connected()) return true;
  
  Serial.print("[MQTT] Attempting connection... ");
  
  String clientId = String(MQTT_CLIENT_ID) + getMACAddress();
  
  if (mqtt.connect(clientId.c_str())) {
    Serial.println("SUCCESS");
    
    // Subscribe to topics
    mqtt.subscribe("swsc/config/#", 1);
    mqtt.subscribe("swsc/control/#", 1);
    mqtt.subscribe("swsc/alert/#", 1);
    
    Serial.println("[MQTT] Subscribed to topics:");
    Serial.println("  - swsc/config/#");
    Serial.println("  - swsc/control/#");
    Serial.println("  - swsc/alert/#");
    
    // Publish online status
    publishStatus("ready");
    
    return true;
  } else {
    Serial.print("FAILED, rc=");
    Serial.println(mqtt.state());
    return false;
  }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  
  String topicStr = String(topic);
  
  Serial.print("[MQTT] << ");
  Serial.print(topicStr);
  Serial.print(" : ");
  Serial.println(message);
  
  handleMQTTMessage(topicStr, message);
}

void handleMQTTMessage(String topic, String payload) {
  // Configuration messages
  if (topic == "swsc/config/duration") {
    state.studyDuration = payload.toInt();
    Serial.printf("[CONFIG] Study duration: %d minutes\n", state.studyDuration);
    state.configReady = true;
  }
  else if (topic == "swsc/config/break_interval") {
    state.breakInterval = payload.toInt();
    Serial.printf("[CONFIG] Break interval: %d minutes\n", state.breakInterval);
  }
  else if (topic == "swsc/config/break_length") {
    state.breakLength = payload.toInt();
    Serial.printf("[CONFIG] Break length: %d minutes\n", state.breakLength);
  }
  else if (topic == "swsc/config/water_reminder") {
    state.waterReminderEnabled = (payload == "on");
    Serial.printf("[CONFIG] Water reminder: %s\n", state.waterReminderEnabled ? "ON" : "OFF");
  }
  
  // Control messages
  else if (topic == "swsc/control/start") {
    if (payload == "START") {
      startSystem();
    }
  }
  else if (topic == "swsc/control/stop") {
    if (payload == "STOP") {
      stopSystem();
    }
  }
  else if (topic == "swsc/control/reset") {
    if (payload == "RESET") {
      resetSystem();
    }
  }
  
  // Alert messages (from Flask)
  else if (topic.startsWith("swsc/alert/water")) {
    if (payload.startsWith("START") || payload.startsWith("PING")) {
      // Water alert triggered by Flask
      if (!buzzerActive) {
        Serial.println("[ALERT] Water reminder from Flask");
        startBuzzer(1000); // 1 second beep
        ledColor(0, 0, 255); // Blue LED
      }
    }
    else if (payload.startsWith("STOP")) {
      // User acknowledged water intake
      Serial.println("[ALERT] Water reminder acknowledged");
      stopWaterAlert();
    }
  }
  else if (topic == "swsc/alert/break") {
    if (payload == "START") {
      Serial.println("[ALERT] Break time from Flask");
      triggerBreakAlert();
    }
    else if (payload == "END") {
      Serial.println("[ALERT] Break ended from Flask");
      ledColor(0, 255, 0); // Back to green
    }
  }
}

// ════════════════════════════════════════════════════════════════
//                       SYSTEM CONTROL
// ════════════════════════════════════════════════════════════════

void startSystem() {
  if (!state.configReady || state.studyDuration == 0) {
    Serial.println("[ERROR] Cannot start - configuration incomplete!");
    Serial.printf("  Duration: %d, Interval: %d\n", state.studyDuration, state.breakInterval);
    publishStatus("config_error");
    return;
  }
  
  Serial.println("\n╔═══════════════════════════════════════╗");
  Serial.println("║       STUDY SESSION STARTED           ║");
  Serial.println("╚═══════════════════════════════════════╝");
  Serial.printf("  Duration: %d minutes\n", state.studyDuration);
  Serial.printf("  Break Interval: %d minutes\n", state.breakInterval);
  Serial.printf("  Break Length: %d minutes\n", state.breakLength);
  Serial.printf("  Water Reminder: %s\n\n", state.waterReminderEnabled ? "ON" : "OFF");
  
  state.active = true;
  state.onBreak = false;
  state.startTime = millis();
  state.intervalStartTime = millis();
  state.lastWaterCheck = millis();
  state.currentPhase = "Study";
  
  ledColor(0, 255, 0); // Green = active
  startBuzzer(200);
  delay(300);
  startBuzzer(200); // Double beep for start
  
  publishStatus("active");
  Serial.println("[STATUS] System is now ACTIVE\n");
}

void stopSystem() {
  Serial.println("\n[STOP] Stopping system...");
  
  state.active = false;
  state.onBreak = false;
  state.currentPhase = "Idle";
  
  digitalWrite(BUZZER_PIN, LOW);
  ledColor(255, 0, 0); // Red = stopped
  
  startBuzzer(150);
  delay(200);
  startBuzzer(150);
  delay(200);
  startBuzzer(150); // Triple beep for stop
  
  publishStatus("stopped");
  
  delay(2000);
  showWaiting();
  ledColor(0, 0, 255); // Blue = waiting
  
  Serial.println("[STATUS] System stopped. Waiting for new session.\n");
}

void resetSystem() {
  Serial.println("\n[RESET] Resetting system...");
  publishStatus("resetting");
  delay(500);
  ESP.restart();
}

// ════════════════════════════════════════════════════════════════
//                      SENSOR & MONITORING
// ════════════════════════════════════════════════════════════════

void readSensors() {
  // Read temperature and humidity
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  
  if (!isnan(t) && !isnan(h)) {
    state.temperature = t;
    state.humidity = h;
  } else {
    Serial.println("[WARNING] DHT sensor read failed");
  }
  
  // Read light sensor (LDR)
  int ldrRaw = analogRead(LDR_PIN);
  // Map ADC value (0-4095) to approximate lux (0-1000)
  state.lightValue = map(ldrRaw, 0, 4095, 0, 1000);
  
  Serial.printf("[SENSOR] Temp: %.1f°C | Humidity: %.0f%% | Light: %d lux\n", 
                state.temperature, state.humidity, state.lightValue);
}

void checkEnvironment() {
  String oldStatus = state.environmentStatus;
  
  if (state.temperature > TEMP_MAX) {
    state.environmentStatus = "Too Hot";
  }
  else if (state.temperature < TEMP_MIN) {
    state.environmentStatus = "Too Cold";
  }
  else if (state.humidity > HUM_MAX) {
    state.environmentStatus = "Too Humid";
  }
  else if (state.humidity < HUM_MIN) {
    state.environmentStatus = "Too Dry";
  }
  else if (state.lightValue < LIGHT_MIN) {
    state.environmentStatus = "Too Dark";
  }
  else if (state.lightValue > LIGHT_MAX) {
    state.environmentStatus = "Too Bright";
  }
  else {
    state.environmentStatus = "Ideal";
  }
  
  // Publish if status changed
  if (state.environmentStatus != oldStatus) {
    Serial.printf("[ENVIRONMENT] Status changed: %s -> %s\n", 
                  oldStatus.c_str(), state.environmentStatus.c_str());
    mqtt.publish("swsc/alert/environment", state.environmentStatus.c_str(), true);
    
    // Alert if not ideal
    if (state.environmentStatus != "Ideal") {
      startBuzzer(100);
      ledColor(255, 100, 0); // Orange warning
    }
  }
}

void checkTimers() {
  if (!state.active) return;
  
  unsigned long now = millis();
  unsigned long intervalElapsed = (now - state.intervalStartTime) / 60000; // minutes
  
  if (!state.onBreak) {
    // Check if it's time for a break
    if (state.breakInterval > 0 && intervalElapsed >= state.breakInterval) {
      Serial.println("\n[TIMER] Break interval reached!");
      state.onBreak = true;
      state.currentPhase = "Break";
      state.intervalStartTime = now;
      
      triggerBreakAlert();
      mqtt.publish("swsc/alert/break", "START", true);
    }
  }
  else {
    // Check if break is over
    if (intervalElapsed >= state.breakLength) {
      Serial.println("[TIMER] Break ended!");
      state.onBreak = false;
      state.currentPhase = "Study";
      state.intervalStartTime = now;
      
      ledColor(0, 255, 0); // Back to green
      mqtt.publish("swsc/alert/break", "END", true);
    }
  }
}

void checkWaterReminder() {
  if (!state.active || !state.waterReminderEnabled) return;
  
  unsigned long now = millis();
  unsigned long waterElapsed = (now - state.lastWaterCheck) / 60000; // minutes
  
  if (waterElapsed >= state.waterInterval) {
    Serial.println("\n[WATER] Time to drink water!");
    state.lastWaterCheck = now;
    
    triggerWaterAlert();
    // Note: Flask will also send water alerts based on its own schedule
    // This is a backup mechanism
  }
}

// ════════════════════════════════════════════════════════════════
//                         ALERTS
// ════════════════════════════════════════════════════════════════

void triggerBreakAlert() {
  Serial.println("[ALERT] >>> BREAK TIME! <<<");
  
  // Triple beep pattern with LED
  for (int i = 0; i < 3; i++) {
    ledColor(255, 100, 0); // Orange
    startBuzzer(200);
    delay(300);
    ledColor(0, 0, 0);
    delay(200);
  }
  
  ledColor(255, 100, 0); // Keep orange during break
}

void triggerWaterAlert() {
  Serial.println("[ALERT] >>> DRINK WATER! <<<");
  
  ledColor(0, 0, 255); // Blue for water
  startBuzzer(150);
  delay(200);
  startBuzzer(150);
  delay(200);
  startBuzzer(150);
}

void stopWaterAlert() {
  digitalWrite(BUZZER_PIN, LOW);
  buzzerActive = false;
  
  if (state.active) {
    ledColor(0, 255, 0); // Back to green
  }
}

// ════════════════════════════════════════════════════════════════
//                      DISPLAY FUNCTIONS
// ════════════════════════════════════════════════════════════════

void updateDisplay() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  
  if (!state.active) {
    showWaiting();
    return;
  }
  
  // Line 1: Sensor data
  display.setCursor(0, 0);
  display.printf("%.1fC %d%% %dlux", 
                 state.temperature, (int)state.humidity, state.lightValue);
  
  // Line 2: Environment status
  display.setCursor(0, 12);
  display.printf("Env: %s", state.environmentStatus.c_str());
  
  // Line 3: Total elapsed
  unsigned long totalElapsed = (millis() - state.startTime) / 60000;
  display.setCursor(0, 24);
  display.printf("Total: %lu/%dm", totalElapsed, state.studyDuration);
  
  // Line 4: Current phase timer
  unsigned long intervalElapsed = millis() - state.intervalStartTime;
  unsigned long phaseDuration = (state.onBreak ? state.breakLength : state.breakInterval) * 60UL * 1000UL;
  unsigned long remaining = (intervalElapsed < phaseDuration) ? (phaseDuration - intervalElapsed) : 0;
  
  int remMin = remaining / 60000;
  int remSec = (remaining / 1000) % 60;
  
  display.setCursor(0, 36);
  display.printf("%s: %02d:%02d", state.currentPhase.c_str(), remMin, remSec);
  
  // Line 5: Progress percentage
  int progress = 0;
  if (state.studyDuration > 0) {
    progress = min(100, (int)((totalElapsed * 100) / state.studyDuration));
  }
  display.setCursor(0, 48);
  display.printf("Progress: %d%%", progress);
  
  // Progress bar
  display.drawRect(0, 58, 128, 6, SSD1306_WHITE);
  if (progress > 0) {
    int barWidth = (progress * 126) / 100;
    display.fillRect(1, 59, barWidth, 4, SSD1306_WHITE);
  }
  
  display.display();
}

void showSplash() {
  display.clearDisplay();
  display.setTextSize(2);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(35, 10);
  display.print("SWSC");
  
  display.setTextSize(1);
  display.setCursor(15, 35);
  display.print("Study Companion");
  
  display.setCursor(35, 50);
  display.print("v2.0");
  
  display.display();
}

void showWaiting() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  
  display.setCursor(0, 5);
  display.println("=== SWSC Ready ===");
  
  display.setCursor(0, 20);
  display.print("WiFi: ");
  display.println(WiFi.status() == WL_CONNECTED ? "Connected" : "Disconnected");
  
  display.setCursor(0, 32);
  display.print("MQTT: ");
  display.println(mqtt.connected() ? "Connected" : "Disconnected");
  
  display.setCursor(0, 50);
  display.println("Waiting for config...");
  
  display.display();
}

// ════════════════════════════════════════════════════════════════
//                      MQTT PUBLISHING
// ════════════════════════════════════════════════════════════════

void publishSensorData() {
  if (!mqtt.connected()) return;
  
  char buffer[16];
  
  // Temperature
  dtostrf(state.temperature, 4, 1, buffer);
  mqtt.publish("swsc/data/temperature", buffer, true);
  
  // Humidity
  dtostrf(state.humidity, 4, 1, buffer);
  mqtt.publish("swsc/data/humidity", buffer, true);
  
  // Light
  sprintf(buffer, "%d", state.lightValue);
  mqtt.publish("swsc/data/light", buffer, true);
  
  // Elapsed time
  unsigned long elapsedMin = (millis() - state.startTime) / 60000;
  sprintf(buffer, "%lu", elapsedMin);
  mqtt.publish("swsc/data/elapsed", buffer, false);
  
  // Progress
  int progress = 0;
  if (state.studyDuration > 0) {
    progress = min(100, (int)((elapsedMin * 100) / state.studyDuration));
  }
  sprintf(buffer, "%d", progress);
  mqtt.publish("swsc/data/progress", buffer, false);
}

void publishStatus(String status) {
  if (mqtt.connected()) {
    mqtt.publish("swsc/status/system", status.c_str(), true);
    Serial.printf("[MQTT] >> Status: %s\n", status.c_str());
  }
}

// ════════════════════════════════════════════════════════════════
//                      UTILITY FUNCTIONS
// ════════════════════════════════════════════════════════════════

void ledColor(int r, int g, int b) {
  analogWrite(LED_RED, r);
  analogWrite(LED_GREEN, g);
  analogWrite(LED_BLUE, b);
}

void startBuzzer(int durationMs) {
  buzzerActive = true;
  buzzerStartTime = millis();
  buzzerDuration = durationMs;
  tone(BUZZER_PIN, 1000); // 1kHz tone
}

void updateBuzzer() {
  if (buzzerActive) {
    if (millis() - buzzerStartTime >= buzzerDuration) {
      noTone(BUZZER_PIN);
      digitalWrite(BUZZER_PIN, LOW);
      buzzerActive = false;
    }
  }
}

String getMACAddress() {
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char macStr[18];
  sprintf(macStr, "%02X%02X%02X%02X%02X%02X", 
          mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  return String(macStr);
}