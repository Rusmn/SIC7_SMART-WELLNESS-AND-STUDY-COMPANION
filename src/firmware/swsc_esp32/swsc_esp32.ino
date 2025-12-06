#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>

const char* WIFI_SSID = "AworaworG";
const char* WIFI_PASS = "HRRZYA22";
const char* MQTT_SERVER = "broker.hivemq.com";
const int MQTT_PORT = 1883;

#define DHT_PIN 4
#define DHT_TYPE DHT11
#define LDR_PIN 34
#define BUZZER_PIN 26
#define LED_RED 19
#define LED_GREEN 23
#define LED_BLUE 25
#define OLED_WIDTH 128
#define OLED_HEIGHT 64

WiFiClient espClient;
PubSubClient mqtt(espClient);
Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);
DHT dht(DHT_PIN, DHT_TYPE);

int cfg_dur = 0;
int cfg_break_int = 0;
int cfg_break_len = 0;
bool cfg_water = false;
bool cfg_ready = false;
bool running = false;
bool in_break = false;
bool water_active[32] = {false};
unsigned long lastSensor = 0;

void setup() {
  Serial.begin(115200);
  pinMode(BUZZER_PIN, OUTPUT); 
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  pinMode(LDR_PIN, INPUT);
  
  dht.begin();
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while(WiFi.status() != WL_CONNECTED) delay(500);
  
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(callback);
}

void callback(char* topic, byte* payload, unsigned int len) {
  String msg;
  for(int i=0; i<len; i++) msg += (char)payload[i];

  if(String(topic) == "swsc/config/duration") cfg_dur = msg.toInt();
  else if(String(topic) == "swsc/config/break_interval") cfg_break_int = msg.toInt();
  else if(String(topic) == "swsc/config/break_length") cfg_break_len = msg.toInt();
  else if(String(topic) == "swsc/control/start") {
    running = true; in_break = false;
    digitalWrite(LED_GREEN, HIGH);
    tone(BUZZER_PIN, 1500, 200);
  }
  else if(String(topic) == "swsc/control/stop") {
    running = false; 
    digitalWrite(LED_GREEN, LOW);
    digitalWrite(LED_RED, LOW);
  }
  else if(String(topic) == "swsc/alert/break") {
    if(msg == "START") { in_break = true; digitalWrite(LED_RED, HIGH); tone(BUZZER_PIN, 1500, 500); }
    else { in_break = false; digitalWrite(LED_RED, LOW); }
  }
  
  cfg_ready = (cfg_dur > 0);
}

void reconnect() {
  while (!mqtt.connected()) {
    String id = "SWSC_ESP32_" + String((uint32_t)ESP.getEfuseMac(), HEX);
    if (mqtt.connect(id.c_str())) {
      mqtt.subscribe("swsc/config/#");
      mqtt.subscribe("swsc/control/#");
      mqtt.subscribe("swsc/alert/#");
    } else delay(1000);
  }
}

void loop() {
  if (!mqtt.connected()) reconnect();
  mqtt.loop();

  if (millis() - lastSensor > 2000) {
    lastSensor = millis();
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    int l = digitalRead(LDR_PIN) == LOW ? 1 : 0;
    
    if(!isnan(t)) mqtt.publish("swsc/data/temperature", String(t).c_str());
    if(!isnan(h)) mqtt.publish("swsc/data/humidity", String(h).c_str());
    mqtt.publish("swsc/data/light", String(l).c_str());
    
    display.clearDisplay();
    display.setCursor(0,0); display.setTextColor(WHITE);
    display.printf("T:%.1f H:%.1f L:%d\n", t, h, l);
    display.printf("Status: %s\n", running ? (in_break?"BREAK":"RUN") : "IDLE");
    display.display();
  }
}