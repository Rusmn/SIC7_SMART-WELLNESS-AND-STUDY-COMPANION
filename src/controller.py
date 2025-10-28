from flask import Flask, render_template, request, jsonify
import threading
import time
import paho.mqtt.client as mqtt

# ---------- MQTT CONFIG ----------
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

# ---------- APP ----------
app = Flask(__name__)

# Sensor/info cache for navbar (updated via MQTT)
sensor_data = {
    "temperature": "-",
    "humidity": "-",
    "light": "-"
}
system_status = "Disconnected"

# ---------- TIMER STATE (owned by backend) ----------
class TimerState:
    def __init__(self):
        self.lock = threading.Lock()
        self.session_length_min = 25
        self.break_length_min = 5
        self.phase = "session"     # "session" | "break"
        self.remaining_sec = self.session_length_min * 60
        self.running = False
        self._last_tick = None
        self.auto_cycle = True     # session -> break -> session ...

    def set_lengths(self, session_min: int, break_min: int):
        with self.lock:
            self.session_length_min = max(1, session_min)
            self.break_length_min = max(1, break_min)
            # Reset remaining according to phase only when not running
            if not self.running:
                self.remaining_sec = (self.session_length_min if self.phase == "session"
                                      else self.break_length_min) * 60

    def start(self):
        with self.lock:
            self.running = True
            self._last_tick = time.time()

    def reset(self):
        with self.lock:
            self.running = False
            self.phase = "session"
            self.remaining_sec = self.session_length_min * 60
            self._last_tick = None

    def stop(self):
        with self.lock:
            self.running = False
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
                if self.auto_cycle:
                    if self.phase == "session":
                        self.phase = "break"
                        self.remaining_sec = self.break_length_min * 60
                    else:
                        self.phase = "session"
                        self.remaining_sec = self.session_length_min * 60
                else:
                    self.running = False

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

# ---------- BACKGROUND LOOPS ----------
def timer_loop():
    while True:
        timer.tick()
        time.sleep(1)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(TOPIC_STATUS)
        client.subscribe(TOPIC_DATA)
        client.subscribe(TOPIC_ALERT)

def on_message(client, userdata, msg):
    global system_status, sensor_data
    t = msg.topic
    payload = msg.payload.decode("utf-8", errors="ignore")
    if t == "swsc/status/system":
        system_status = payload
    elif t == "swsc/data/temperature":
        sensor_data["temperature"] = payload
    elif t == "swsc/data/humidity":
        sensor_data["humidity"] = payload
    elif t == "swsc/data/light":
        sensor_data["light"] = payload

def mqtt_loop():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
    client.loop_forever()

# ---------- HTTP ROUTES ----------
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
        light=sensor_data["light"],
    )

@app.route("/timer", methods=["GET"])
def get_timer():
    return jsonify(timer.snapshot())

@app.route("/status", methods=["GET"])
def get_status():
    return jsonify({
        "system_status": system_status,
        "temperature": sensor_data["temperature"],
        "humidity": sensor_data["humidity"],
        "light": sensor_data["light"]
    })

@app.route("/start", methods=["POST"])
def start():
    data = request.get_json(silent=True) or {}
    session_min = int(data.get("session_length_min", timer.session_length_min))
    break_min = int(data.get("break_length_min", timer.break_length_min))

    timer.set_lengths(session_min, break_min)
    timer.start()

    try:
        # Push config to hardware and start
        mqttc = mqtt.Client()
        mqttc.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        mqttc.loop_start()
        mqttc.publish(TOPIC_CONFIG_DURATION, str(session_min))
        mqttc.publish(TOPIC_CONFIG_BREAK, str(break_min))
        mqttc.publish(TOPIC_CONTROL_START, "START")
        time.sleep(0.2)
        mqttc.loop_stop()
        mqttc.disconnect()
    except Exception:
        pass

    return jsonify({"ok": True})

@app.route("/reset", methods=["POST"])
def reset():
    timer.reset()
    try:
        mqttc = mqtt.Client()
        mqttc.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        mqttc.loop_start()
        mqttc.publish(TOPIC_CONTROL_RESET, "RESET")
        time.sleep(0.2)
        mqttc.loop_stop()
        mqttc.disconnect()
    except Exception:
        pass
    return jsonify({"ok": True})

@app.route("/stop", methods=["POST"])
def stop():
    timer.stop()
    try:
        mqttc = mqtt.Client()
        mqttc.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        mqttc.loop_start()
        mqttc.publish(TOPIC_CONTROL_STOP, "STOP")
        time.sleep(0.2)
        mqttc.loop_stop()
        mqttc.disconnect()
    except Exception:
        pass
    return jsonify({"ok": True})

# ---------- BOOTSTRAP ----------
if __name__ == "__main__":
    threading.Thread(target=timer_loop, daemon=True).start()
    threading.Thread(target=mqtt_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
