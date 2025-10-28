/*
 * ═══════════════════════════════════════════════════════════════
 * SMART WELLNESS & STUDY COMPANION (SWSC) - FE Version
 * ═══════════════════════════════════════════════════════════════
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>

// ============== CONFIG ==============
const char* WIFI_SSID = "AworaworG";      // ← Your WiFi SSID
const char* WIFI_PASSWORD = "HRRZYA22";  // ← Your WiFi Password
const char* MQTT_SERVER = "broker.hivemq.com";
const int MQTT_PORT = 1883;

// ============== PINS ==============
#define DHT_PIN 4
#define LDR_PIN 34
#define BUZZER_PIN 18 // Controls Transistor Base
#define LED_RED 19
#define LED_GREEN 23
#define LED_BLUE 25

// ============== OBJECTS ==============
WiFiClient espClient;
PubSubClient mqtt(espClient);
DHT dht(DHT_PIN, DHT11);

// ============== GLOBAL VARIABLES ==============
bool systemActive = false;
bool configReceived = false; // Flag that backend sent initial config
int studyDuration = 0;       // Received from backend
int breakInterval = 0;       // Received from backend
int breakLength = 0;         // Received from backend
bool waterReminderEnabled = true; // Controlled by backend

unsigned long studyStartTime = 0; // For calculating 'elapsed' time
unsigned long lastMQTTPublish = 0;
unsigned long lastLedBlink = 0;
const long LED_BLINK_INTERVAL = 500;
const unsigned long MQTT_PUBLISH_INTERVAL = 5000;

// Sensor thresholds for environment alerts
const float TEMP_MIN = 20.0;
const float TEMP_MAX = 30.0;
const float HUMIDITY_MIN = 40.0;
const float HUMIDITY_MAX = 70.0;

String environmentStatus = "Waiting...";
float currentTemp = 0;
float currentHumidity = 0;
int currentLight = 0; // 0 = Dark, 1000 = Bright

bool breakAlertActive = false;
bool waterAlertActive = false;

// ============== FUNCTION PROTOTYPES ==============
void setupWiFi();
void reconnectMQTT();
void mqttCallback(char* topic, byte* payload, unsigned int length);
void startSystem();
void stopSystem();
void checkEnvironment(float temp, float humidity, int light);
void triggerBreakAlertStart();
void triggerBreakAlertEnd();
void triggerWaterAlertStart();
void triggerWaterAlertStop();
void publishSensorData();
void publishStatus(String status);
void beep(int duration);
void handleStatusLed();

// ============== SETUP ==============
void setup() {
  Serial.begin(115200);
  Serial.println("\n=========================================");
  Serial.println("  SWSC - Smart Study Companion");
  Serial.println("  FE Version (No OLED)");
  Serial.println("=========================================");

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  pinMode(LDR_PIN, INPUT);

  digitalWrite(LED_RED, LOW);
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_BLUE, LOW);

  dht.begin();
  Serial.println("(+) DHT11 initialized");

  setupWiFi();

  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(mqttCallback);

  reconnectMQTT(); // Initial connection attempt

  Serial.println("\n(+) System Ready!");
  Serial.println("-----------------------------------------");
  Serial.println("Waiting for configuration via MQTT...");
  Serial.println("-----------------------------------------\n");
}

// ============== MAIN LOOP ==============
void loop() {
  if (!mqtt.connected()) {
    reconnectMQTT(); // Attempt to reconnect if disconnected
  }
  mqtt.loop(); // Process incoming MQTT messages

  handleStatusLed(); // Update status LED (Blue blink / Green solid)

  if (!systemActive) {
    delay(100); // Reduce CPU usage when idle
    return;
  }

  // --- SYSTEM ACTIVE ---
  // Read Sensors
  currentTemp = dht.readTemperature();
  currentHumidity = dht.readHumidity();
  int lightDigitalValue = digitalRead(LDR_PIN);
  currentLight = (lightDigitalValue == HIGH) ? 0 : 1000; // HIGH = Dark

  if (isnan(currentTemp) || isnan(currentHumidity)) {
    currentTemp = 0; currentHumidity = 0;
  }

  // Check Environment & potentially send MQTT alert
  checkEnvironment(currentTemp, currentHumidity, currentLight);

  // Publish sensor data periodically
  if (millis() - lastMQTTPublish >= MQTT_PUBLISH_INTERVAL) {
    publishSensorData();
    lastMQTTPublish = millis();
  }

  delay(100); // Small delay
}

// ============== WIFI CONNECTION ==============
void setupWiFi() {
  Serial.print("\nConnecting to WiFi: ");
  Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n(+) WiFi Connected!");
    Serial.print("IP Address: "); Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n(-) WiFi Connection FAILED!");
  }
}

// ============== MQTT CONNECTION ==============
void reconnectMQTT() {
  while (!mqtt.connected()) {
    Serial.print("Connecting to MQTT broker... ");
    // Ensure WiFi is connected before attempting MQTT connection
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("\n(-) WiFi disconnected! Waiting...");
        delay(1000);
        continue; // Retry WiFi check
    }

    String clientId = "SWSC_ESP32_";
    clientId += String(random(0xffff), HEX);

    delay(500); // Give network stack some time

    if (mqtt.connect(clientId.c_str())) {
      Serial.println("CONNECTED!");
      // Subscribe to all necessary topics
      mqtt.subscribe("swsc/config/#");
      mqtt.subscribe("swsc/control/#");
      mqtt.subscribe("swsc/alert/break");
      mqtt.subscribe("swsc/alert/water");
      Serial.println("(+) Subscribed to necessary topics");
      publishStatus("ready"); // Inform backend that ESP32 is ready
    } else {
      Serial.print("FAILED, rc="); Serial.println(mqtt.state());
      Serial.println("Retrying in 5 seconds...");
      delay(5000);
    }
  }
}

// ============== MQTT MESSAGE HANDLER ==============
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) { message += (char)payload[i]; }

  Serial.println("\n[MQTT RECV]");
  Serial.print("  Topic: "); Serial.println(topic);
  Serial.print("  Message: "); Serial.println(message);

  String topicStr = String(topic);

  // Configuration Topics
  if (topicStr == "swsc/config/duration") {
    studyDuration = message.toInt();
    Serial.println("  -> Study duration received");
    configReceived = true;
  } else if (topicStr == "swsc/config/break_interval") {
    breakInterval = message.toInt();
    Serial.println("  -> Break interval received");
  } else if (topicStr == "swsc/config/break_length") {
    breakLength = message.toInt();
    Serial.println("  -> Break length received");
  } else if (topicStr == "swsc/config/water_reminder") {
    waterReminderEnabled = (message == "on");
    Serial.print("  -> Water reminder: "); Serial.println(waterReminderEnabled ? "ON" : "OFF");
  }
  // Control Topics
  else if (topicStr == "swsc/control/start") {
    if (configReceived) {
      Serial.println("\n=============== STARTING SYSTEM ===============");
      startSystem();
    } else {
      Serial.println("(-) ERROR: Configuration not received yet!");
      mqtt.publish("swsc/status/error", "Config not received");
    }
  } else if (topicStr == "swsc/control/stop") {
    Serial.println("\n[STOP] STOPPING SYSTEM...");
    stopSystem();
  } else if (topicStr == "swsc/control/reset") {
    Serial.println("\n[RESET] RESETTING ESP32...");
    publishStatus("Resetting...");
    delay(500);
    ESP.restart();
  }
  // Alert Topics (Commands from Backend)
  else if (topicStr == "swsc/alert/break") {
    if (message == "START") { triggerBreakAlertStart(); }
    else if (message == "END") { triggerBreakAlertEnd(); }
  } else if (topicStr == "swsc/alert/water") {
    if (message.startsWith("START")) { triggerWaterAlertStart(); }
    else if (message.startsWith("STOP")) { triggerWaterAlertStop(); }
    else if (message.startsWith("PING")) {
      if (waterAlertActive) { beep(50); } // Short reminder beep
    }
  }
}

// ============== SYSTEM CONTROL ==============
void startSystem() {
  systemActive = true;
  studyStartTime = millis();
  lastMQTTPublish = millis();
  breakAlertActive = false;
  waterAlertActive = false;
  handleStatusLed(); // Turn Green LED ON
  publishStatus("active");
  Serial.println("(+) System ACTIVE!");
}

void stopSystem() {
  systemActive = false;
  breakAlertActive = false;
  waterAlertActive = false;
  digitalWrite(LED_RED, LOW);
  digitalWrite(LED_BLUE, LOW);
  handleStatusLed(); // Start blinking Blue LED
  publishStatus("stopped");
  Serial.println("(+) System STOPPED!");
}

// ============== ENVIRONMENT CHECK ==============
void checkEnvironment(float temp, float humidity, int light) {
  String lastStatus = environmentStatus;
  bool alertSent = false; // Flag to only send one type of alert per check

  if (temp > TEMP_MAX) {
    environmentStatus = "PANAS!";
    mqtt.publish("swsc/alert/environment", "Temperature too high!");
    alertSent = true;
  } else if (temp < TEMP_MIN) {
    environmentStatus = "Dingin";
  }

  if (!alertSent && humidity < HUMIDITY_MIN) {
     environmentStatus = "Kering";
     // mqtt.publish("swsc/alert/environment", "Humidity too low!"); // Optional alert
  } else if (!alertSent && humidity > HUMIDITY_MAX) {
     environmentStatus = "Lembab";
     // mqtt.publish("swsc/alert/environment", "Humidity too high!"); // Optional alert
  }

  if (!alertSent && light == 0) { // Dark
    environmentStatus = "Gelap";
    mqtt.publish("swsc/alert/environment", "Light level too low!");
    alertSent = true;
  } else if (light == 1000 && !alertSent && environmentStatus != "PANAS!") { // Only set to Terang if not already Hot
     environmentStatus = "Terang";
  }

  // Check for Ideal conditions only if no bad conditions were detected
  if (!alertSent && temp >= TEMP_MIN && temp <= TEMP_MAX &&
      humidity >= HUMIDITY_MIN && humidity <= HUMIDITY_MAX &&
      light == 1000) {
    environmentStatus = "Ideal";
  }

  // Publish environment status change (optional)
  if (environmentStatus != lastStatus) {
     mqtt.publish("swsc/status/environment", environmentStatus.c_str());
  }
}

// ============== ALERT TRIGGERS ==============
void triggerBreakAlertStart() {
  Serial.println("[ALERT] Break Alert START received");
  breakAlertActive = true;
  for (int i = 0; i < 5; i++) {
    if (!systemActive) { breakAlertActive = false; digitalWrite(LED_RED, LOW); return; } // Exit if stopped
    digitalWrite(LED_RED, HIGH);
    beep(200);
    delay(100);
    digitalWrite(LED_RED, LOW);
    delay(100);
  }
  digitalWrite(LED_RED, LOW); // Ensure LED is off after sequence
  breakAlertActive = false;   // Assume alert sequence completion
}

void triggerBreakAlertEnd() {
  Serial.println("[ALERT] Break Alert END received");
  breakAlertActive = false;
  digitalWrite(LED_RED, LOW);
}

void triggerWaterAlertStart() {
  if (!waterReminderEnabled) return;
  Serial.println("[ALERT] Water Alert START received");
  waterAlertActive = true;
  for (int i = 0; i < 3; i++) {
     if (!systemActive) { waterAlertActive = false; digitalWrite(LED_BLUE, LOW); return; } // Exit if stopped
    digitalWrite(LED_BLUE, HIGH);
    beep(150);
    delay(100);
    digitalWrite(LED_BLUE, LOW);
    delay(100);
  }
  // Keep waterAlertActive = true until STOP message is received
}

void triggerWaterAlertStop() {
  Serial.println("[ALERT] Water Alert STOP received");
  waterAlertActive = false;
  digitalWrite(LED_BLUE, LOW);
}

// ============== DATA PUBLISHING ==============
void publishSensorData() {
  char buffer[10];

  dtostrf(currentTemp, 4, 1, buffer);
  mqtt.publish("swsc/data/temperature", buffer);

  dtostrf(currentHumidity, 4, 1, buffer);
  mqtt.publish("swsc/data/humidity", buffer);

  sprintf(buffer, "%d", currentLight);
  mqtt.publish("swsc/data/light", buffer);

  unsigned long elapsedMin = 0;
  if (studyStartTime > 0) {
      elapsedMin = (millis() - studyStartTime) / 60000;
  }
  sprintf(buffer, "%lu", elapsedMin);
  mqtt.publish("swsc/data/elapsed", buffer);

  // Progress is handled by backend, send placeholder
  mqtt.publish("swsc/data/progress", "0");
}

void publishStatus(String status) {
  mqtt.publish("swsc/status/system", status.c_str());
}

// ============== UTILITIES ==============
void beep(int duration) {
    tone(BUZZER_PIN, 1000);
    delay(duration);
    noTone(BUZZER_PIN);
}

void handleStatusLed() {
  if (systemActive) {
    digitalWrite(LED_BLUE, LOW);
    digitalWrite(LED_GREEN, HIGH);
  } else {
    digitalWrite(LED_GREEN, LOW);
    if (millis() - lastLedBlink > LED_BLINK_INTERVAL) {
      digitalWrite(LED_BLUE, !digitalRead(LED_BLUE));
      lastLedBlink = millis();
    }
  }
}