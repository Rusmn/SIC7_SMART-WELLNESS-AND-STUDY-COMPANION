/*
 * SMART WELLNESS & STUDY COMPANION (SWSC) - Realtime ESP32
 * - Publikasi sensor tiap 1 detik
 * - Event langsung diproses via MQTT callback (tanpa delay panjang)
 * - LED: Biru (idle blink), Hijau (aktif), Merah (break alert)
 * - Buzzer: break & water alarm
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>

// ====== NETWORK / MQTT ======
const char* WIFI_SSID = "AworaworG";
const char* WIFI_PASSWORD = "HRRZYA22";
const char* MQTT_SERVER = "broker.hivemq.com";
const int   MQTT_PORT   = 1883;

// ====== PINS ======
#define DHT_PIN     4
#define LDR_PIN     34
#define BUZZER_PIN  18
#define LED_RED     19
#define LED_GREEN   23
#define LED_BLUE    25

// ====== OBJECTS ======
WiFiClient espClient;
PubSubClient mqtt(espClient);
DHT dht(DHT_PIN, DHT11);

// ====== STATE ======
bool systemActive = false;
bool configReceived = false;
int  studyDuration = 0;
int  breakInterval = 0;
int  breakLength   = 0;
bool waterReminderEnabled = true;

unsigned long studyStartTime   = 0;
unsigned long lastMQTTPublish  = 0;
unsigned long lastLedBlink     = 0;
const unsigned long LED_BLINK_INTERVAL     = 500;
const unsigned long MQTT_PUBLISH_INTERVAL  = 1000; // 1s → realtime monitoring

// Threshold lingkungan (opsional)
const float TEMP_MIN = 20.0, TEMP_MAX = 30.0;
const float HUMIDITY_MIN = 40.0, HUMIDITY_MAX = 70.0;

String environmentStatus = "Waiting...";
float currentTemp = 0, currentHumidity = 0;
int   currentLight = 0;

bool breakAlertActive = false;
bool waterAlertActive = false;

// ====== DECL ======
void setupWiFi();
void reconnectMQTT();
void mqttCallback(char* topic, byte* payload, unsigned int length);
void startSystem();
void stopSystem();
void checkEnvironment(float t, float h, int l);
void triggerBreakAlertStart();
void triggerBreakAlertEnd();
void triggerWaterAlertStart();
void triggerWaterAlertStop();
void publishSensorData();
void publishStatus(const String& status);
void beep(int duration);
void handleStatusLed();

// ====== SETUP ======
void setup() {
  Serial.begin(115200);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  pinMode(LDR_PIN, INPUT);

  digitalWrite(LED_RED, LOW);
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_BLUE, LOW);

  dht.begin();

  setupWiFi();
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(mqttCallback);

  // LWT (optional)
  mqtt.connect("SWSC_ESP32", nullptr, nullptr, "swsc/status/system", 0, false, "offline");

  reconnectMQTT();
  publishStatus("ready");
}

// ====== LOOP ======
void loop() {
  if (!mqtt.connected()) reconnectMQTT();
  mqtt.loop();

  handleStatusLed();

  if (!systemActive) { delay(1); return; }

  // Baca sensor
  currentTemp = dht.readTemperature();
  currentHumidity = dht.readHumidity();
  int lightDigitalValue = digitalRead(LDR_PIN);
  currentLight = (lightDigitalValue == HIGH) ? 0 : 1000; // HIGH=gelap (pull-up eksternal dapat mempengaruhi)

  if (isnan(currentTemp) || isnan(currentHumidity)) {
    currentTemp = 0; currentHumidity = 0;
  }

  checkEnvironment(currentTemp, currentHumidity, currentLight);

  // Publikasi cepat (1s)
  if (millis() - lastMQTTPublish >= MQTT_PUBLISH_INTERVAL) {
    publishSensorData();
    lastMQTTPublish = millis();
  }

  // jangan blocking
  delay(1);
}

// ====== WIFI ======
void setupWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 40) {
    delay(250);
    tries++;
  }
}

// ====== MQTT ======
void reconnectMQTT() {
  while (!mqtt.connected()) {
    if (WiFi.status() != WL_CONNECTED) { delay(500); continue; }

    String cid = "SWSC_ESP32_" + String((uint32_t)ESP.getEfuseMac(), HEX);
    if (mqtt.connect(cid.c_str(), nullptr, nullptr, "swsc/status/system", 0, false, "offline")) {
      mqtt.subscribe("swsc/config/#");
      mqtt.subscribe("swsc/control/#");
      mqtt.subscribe("swsc/alert/#");
      publishStatus("ready");
    } else {
      delay(1000);
    }
  }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message;
  message.reserve(length);
  for (unsigned int i = 0; i < length; i++) message += (char)payload[i];

  String t = String(topic);

  // Konfigurasi
  if (t == "swsc/config/duration")        { studyDuration = message.toInt(); configReceived = true; }
  else if (t == "swsc/config/break_interval") { breakInterval = message.toInt(); }
  else if (t == "swsc/config/break_length")   { breakLength = message.toInt(); }
  else if (t == "swsc/config/water_reminder") { waterReminderEnabled = (message == "on"); }

  // Kontrol
  else if (t == "swsc/control/start") { if (configReceived) startSystem(); }
  else if (t == "swsc/control/stop")  { stopSystem(); }
  else if (t == "swsc/control/reset") { publishStatus("resetting"); delay(200); ESP.restart(); }

  // Alert dari backend
  else if (t == "swsc/alert/break") {
    if (message == "START") triggerBreakAlertStart();
    else if (message == "END") triggerBreakAlertEnd();
  } else if (t == "swsc/alert/water") {
    if (message.startsWith("START"))      triggerWaterAlertStart();
    else if (message.startsWith("STOP"))  triggerWaterAlertStop();
    else if (message.startsWith("PING"))  { if (waterAlertActive) beep(50); }
  }
}

// ====== CONTROL ======
void startSystem() {
  systemActive = true;
  studyStartTime = millis();
  breakAlertActive = false; waterAlertActive = false;
  publishStatus("active");
}

void stopSystem() {
  systemActive = false;
  breakAlertActive = false; waterAlertActive = false;
  digitalWrite(LED_RED, LOW); digitalWrite(LED_BLUE, LOW);
  publishStatus("stopped");
}

// ====== ENV CHECK ======
void checkEnvironment(float temp, float hum, int light) {
  String last = environmentStatus;
  bool bad = false;

  if (temp > TEMP_MAX) { environmentStatus = "PANAS!"; mqtt.publish("swsc/alert/environment", "Temperature too high!"); bad = true; }
  else if (temp < TEMP_MIN) environmentStatus = "Dingin";

  if (!bad && hum < HUMIDITY_MIN) environmentStatus = "Kering";
  else if (!bad && hum > HUMIDITY_MAX) environmentStatus = "Lembab";

  if (!bad && light == 0) { environmentStatus = "Gelap"; mqtt.publish("swsc/alert/environment", "Light too low!"); bad = true; }
  else if (!bad && environmentStatus != "PANAS!") environmentStatus = "Terang";

  if (!bad && temp>=TEMP_MIN && temp<=TEMP_MAX && hum>=HUMIDITY_MIN && hum<=HUMIDITY_MAX && light==1000)
    environmentStatus = "Ideal";

  if (environmentStatus != last) mqtt.publish("swsc/status/environment", environmentStatus.c_str());
}

// ====== ALERTS ======
void triggerBreakAlertStart() {
  breakAlertActive = true;
  for (int i=0;i<5;i++){
    if (!systemActive) { breakAlertActive=false; break; }
    digitalWrite(LED_RED, HIGH); beep(180); delay(100);
    digitalWrite(LED_RED, LOW);  delay(100);
  }
  digitalWrite(LED_RED, LOW);
  breakAlertActive = false;
}

void triggerBreakAlertEnd() {
  breakAlertActive = false;
  digitalWrite(LED_RED, LOW);
}

void triggerWaterAlertStart() {
  if (!waterReminderEnabled) return;
  waterAlertActive = true;
  for (int i=0;i<3;i++){
    if (!systemActive) { waterAlertActive=false; break; }
    digitalWrite(LED_BLUE, HIGH); beep(140); delay(100);
    digitalWrite(LED_BLUE, LOW);  delay(100);
  }
}

void triggerWaterAlertStop() {
  waterAlertActive = false;
  digitalWrite(LED_BLUE, LOW);
}

// ====== PUBLISH ======
void publishSensorData() {
  char buf[12];
  dtostrf(currentTemp,  4,1,buf); mqtt.publish("swsc/data/temperature", buf);
  dtostrf(currentHumidity,4,1,buf); mqtt.publish("swsc/data/humidity", buf);
  sprintf(buf, "%d", currentLight); mqtt.publish("swsc/data/light", buf);

  unsigned long elapsedMin = (studyStartTime>0) ? (millis()-studyStartTime)/60000UL : 0;
  sprintf(buf, "%lu", elapsedMin); mqtt.publish("swsc/data/elapsed", buf);

  mqtt.publish("swsc/data/progress", "0");
}

void publishStatus(const String& s) { mqtt.publish("swsc/status/system", s.c_str()); }

// ====== UTIL ======
void beep(int d){ tone(BUZZER_PIN, 1000); delay(d); noTone(BUZZER_PIN); }

void handleStatusLed() {
  if (systemActive) {
    digitalWrite(LED_BLUE, LOW);
    digitalWrite(LED_GREEN, HIGH);
  } else {
    digitalWrite(LED_GREEN, LOW);
    if (millis()-lastLedBlink > LED_BLINK_INTERVAL) {
      digitalWrite(LED_BLUE, !digitalRead(LED_BLUE));
      lastLedBlink = millis();
    }
  }
}
