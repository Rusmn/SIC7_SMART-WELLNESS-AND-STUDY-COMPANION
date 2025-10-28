import os
import time
import threading
from flask import Flask, render_template, jsonify, request
import paho.mqtt.client as mqtt

# ===================== MQTT CONFIGURATION =====================
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

TOPIC_CONFIG_DURATION = "swsc/config/duration"
TOPIC_CONFIG_BREAK = "swsc/config/break_interval"
TOPIC_CONTROL_START = "swsc/control/start"
TOPIC_CONTROL_STOP = "swsc/control/stop"
TOPIC_CONTROL_RESET = "swsc/control/reset"
TOPIC_STATUS = "swsc/status/#"
TOPIC_DATA = "swsc/data/#"
TOPIC_ALERT = "swsc/alert/#"

# ===================== APP INITIALIZATION =====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=BASE_DIR, static_folder=BASE_DIR)

# ===================== GLOBAL VARIABLES =====================
sensor_data = {"temperature": "-", "humidity": "-", "light": "-"}
system_status = "Disconnected"

# ===================== TIMER CLASS =====================
class TimerState:
    def __init__(self):
        self.session_length_min = 25
        self.break_length_min = 5
        self.phase = "session"
        self.remaining_sec = self.session_length_min * 60
        self.running = False
        self._last_tick = None
        self.lock = threading.Lock()

    def set_lengths(self, session_min, break_min):
        with self.lock:
            self.session_length_min = max(1, int(session_min))
            self.break_length_min = max(1, int(break_min))
            if not self.running:
                self.remaining_sec = self.session_length_min * 60
                self.phase = "session"

    def start(self):
        with self.lock:
            self.running = True
            self._last_tick = time.time()

    def stop(self):
        with self.lock:
            self.running = False

    def reset(self):
        with self.lock:
            self.running = False
            self.phase = "session"
            self.remaining_sec = self.session_length_min * 60
            self._last_tick = None

    def tick(self):
        with self.lock:
            if not self.running:
                return
            now = time.time()
            if self._last_tick is None:
                self._last_tick = now
                return
            elapsed = int(now - self._last_tick)
            if elapsed <= 0:
                return
            self._last_tick = now
            self.remaining_sec = max(0, self.remaining_sec - elapsed)
            if self.remaining_sec == 0:
                if self.phase == "session":
                    self.phase = "break"
                    self.remaining_sec = self.break_length_min * 60
                else:
                    self.phase = "session"
                    self.remaining_sec = self.session_length_min * 60

    def snapshot(self):
        with self.lock:
            return {
                "session_length_min": self.session_length_min,
                "break_length_min": self.break_length_min,
                "phase": self.phase,
                "remaining_sec": self.remaining_sec,
                "running": self.running
            }

timer = TimerState()

# ===================== BACKGROUND THREADS =====================
def timer_loop():
    while True:
        timer.tick()
        time.sleep(1)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker.")
        client.subscribe(TOPIC_STATUS)
        client.subscribe(TOPIC_DATA)
        client.subscribe(TOPIC_ALERT)
    else:
        print("Failed to connect MQTT broker with code:", rc)

def on_message(client, userdata, msg):
    global sensor_data, system_status
    topic = msg.topic
    payload = msg.payload.decode("utf-8", errors="ignore")
    if topic == "swsc/status/system":
        system_status = payload
    elif topic == "swsc/data/temperature":
        sensor_data["temperature"] = payload
    elif topic == "swsc/data/humidity":
        sensor_data["humidity"] = payload
    elif topic == "swsc/data/light":
        sensor_data["light"] = payload

def mqtt_loop():
    try:
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        client.loop_forever()
    except Exception as e:
        print("[WARNING] MQTT connection failed:", e)
        print("Running in local mode (without hardware).")
        while True:
            time.sleep(10)

# ===================== ROUTES =====================
@app.route("/")
def index():
    snap = timer.snapshot()
    return render_template(
        "index.html",
        session_len=snap["session_length_min"],
        break_len=snap["break_length_min"],
        status=system_status,
        temp=sensor_data["temperature"],
        hum=sensor_data["humidity"],
        light=sensor_data["light"]
    )

@app.route("/timer")
def get_timer():
    return jsonify(timer.snapshot())

@app.route("/status")
def get_status():
    return jsonify({
        "temperature": sensor_data["temperature"],
        "humidity": sensor_data["humidity"],
        "light": sensor_data["light"],
        "system_status": system_status
    })

@app.route("/start", methods=["POST"])
def start():
    data = request.get_json(silent=True) or {}
    session_min = data.get("session_length_min", timer.session_length_min)
    break_min = data.get("break_length_min", timer.break_length_min)
    timer.set_lengths(session_min, break_min)
    timer.start()

    try:
        mqttc = mqtt.Client()
        mqttc.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        mqttc.loop_start()
        mqttc.publish(TOPIC_CONFIG_DURATION, str(session_min))
        mqttc.publish(TOPIC_CONFIG_BREAK, str(break_min))
        mqttc.publish(TOPIC_CONTROL_START, "START")
        mqttc.loop_stop()
        mqttc.disconnect()
    except Exception as e:
        print("[WARNING] Could not send MQTT start command:", e)

    return jsonify({"ok": True})

@app.route("/reset", methods=["POST"])
def reset():
    timer.reset()
    try:
        mqttc = mqtt.Client()
        mqttc.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        mqttc.loop_start()
        mqttc.publish(TOPIC_CONTROL_RESET, "RESET")
        mqttc.loop_stop()
        mqttc.disconnect()
    except Exception as e:
        print("[WARNING] Could not send MQTT reset command:", e)
    return jsonify({"ok": True})

@app.route("/stop", methods=["POST"])
def stop():
    timer.stop()
    try:
        mqttc = mqtt.Client()
        mqttc.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        mqttc.loop_start()
        mqttc.publish(TOPIC_CONTROL_STOP, "STOP")
        mqttc.loop_stop()
        mqttc.disconnect()
    except Exception as e:
        print("[WARNING] Could not send MQTT stop command:", e)
    return jsonify({"ok": True})

# ===================== MAIN =====================
if __name__ == "__main__":
    threading.Thread(target=timer_loop, daemon=True).start()
    threading.Thread(target=mqtt_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=True)
