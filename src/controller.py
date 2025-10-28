import os
import time
import threading
from dataclasses import dataclass
from typing import List, Dict, Optional
from flask import Flask, jsonify, render_template, request
import paho.mqtt.client as mqtt

# ============== MQTT CONFIG ==============
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

TOPIC_CONFIG_DURATION        = "swsc/config/duration"
TOPIC_CONFIG_BREAK_INTERVAL  = "swsc/config/break_interval"
TOPIC_CONFIG_BREAK_LENGTH    = "swsc/config/break_length"
TOPIC_CONFIG_WATER_REMINDER  = "swsc/config/water_reminder"

TOPIC_CONTROL_START          = "swsc/control/start"
TOPIC_CONTROL_STOP           = "swsc/control/stop"
TOPIC_CONTROL_RESET          = "swsc/control/reset"

TOPIC_ALERT_BREAK            = "swsc/alert/break"
TOPIC_ALERT_WATER            = "swsc/alert/water"

TOPIC_STATUS = "swsc/status/#"
TOPIC_DATA   = "swsc/data/#"
TOPIC_ALERT  = "swsc/alert/#"

# ============== APP INIT ==============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=BASE_DIR,
    static_folder=BASE_DIR,
    static_url_path=""
)

# ============== SENSOR CACHE ==============
sensor_data = {"temperature": "-", "humidity": "-", "light": "-"}
system_status = "Disconnected"

# ============== STUDY PLAN MODEL ==============
@dataclass
class StudyPlan:
    duration_min: int
    break_interval_min: int
    break_count: int
    break_length_min: int
    water_milestones: List[int]
    water_amount_ml_per: int
    water_total_ml: int

def compute_plan(duration_min: int) -> StudyPlan:
    d = max(1, int(duration_min))
    if d <= 30:
        interval, bcount, blen = d, 0, 0
    elif d <= 60:
        interval, bcount, blen = 30, d // 30, 5
    elif d <= 120:
        interval, bcount, blen = 40, d // 40, 7
    elif d <= 180:
        interval, bcount, blen = 45, d // 45, 10
    else:
        interval, bcount, blen = 60, d // 60, 15

    water_every = 30
    per_ml = 250
    milestone_count = max(1, d // water_every)
    total_ml = milestone_count * per_ml
    water_milestones = [m * 60 * water_every for m in range(1, milestone_count + 1)]

    return StudyPlan(
        duration_min=d,
        break_interval_min=interval,
        break_count=bcount,
        break_length_min=blen,
        water_milestones=water_milestones,
        water_amount_ml_per=per_ml,
        water_total_ml=total_ml
    )

# ============== TIMER / SCHEDULER ==============
class Scheduler:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.phase = "session"
        self.phase_remaining_sec = 0
        self.total_remaining_sec = 0
        self.plan: Optional[StudyPlan] = None

        self._start_epoch = None
        self._last_tick = None
        self._next_session_cut = 0
        self._breaks_left = 0

        self._water_alarm_active: Dict[int, bool] = {}
        self._water_fired: Dict[int, bool] = {}
        self._last_water_buzz: float = 0.0

    def start(self, plan: StudyPlan):
        with self.lock:
            self.plan = plan
            self.running = True
            self.phase = "session"
            self.total_remaining_sec = plan.duration_min * 60
            self._breaks_left = plan.break_count
            self.phase_remaining_sec = min(
                self.total_remaining_sec, plan.break_interval_min * 60
            ) if plan.break_count > 0 else self.total_remaining_sec
            self._start_epoch = time.time()
            self._last_tick = self._start_epoch
            self._next_session_cut = self.phase_remaining_sec
            self._water_alarm_active = {i: False for i in range(len(plan.water_milestones))}
            self._water_fired = {i: False for i in range(len(plan.water_milestones))}
            self._last_water_buzz = 0.0

    def stop(self):
        with self.lock:
            self.running = False
            self._start_epoch = None
            self._last_tick = None
            for i, active in list(self._water_alarm_active.items()):
                if active:
                    _mqtt_safe_publish(TOPIC_ALERT_WATER, f"STOP:{i}")
                    self._water_alarm_active[i] = False

    def reset(self):
        with self.lock:
            self.running = False
            self.phase = "session"
            self.phase_remaining_sec = 0
            self.total_remaining_sec = 0
            self.plan = None
            self._start_epoch = None
            self._last_tick = None
            self._breaks_left = 0
            self._water_alarm_active.clear()
            self._water_fired.clear()
            self._last_water_buzz = 0.0

    def water_ack(self, milestone_id: int):
        with self.lock:
            if self._water_alarm_active.get(milestone_id):
                _mqtt_safe_publish(TOPIC_ALERT_WATER, f"STOP:{milestone_id}")
                self._water_alarm_active[milestone_id] = False

    def tick(self):
        with self.lock:
            if not self.running or self.plan is None or self._last_tick is None:
                return
            now = time.time()
            elapsed = int(now - self._last_tick)
            if elapsed <= 0:
                self._buzz_water_if_needed(now)
                return
            self._last_tick = now

            since_start = int(now - self._start_epoch)
            for idx, tsec in enumerate(self.plan.water_milestones):
                if since_start >= tsec and not self._water_fired.get(idx, False):
                    self._water_fired[idx] = True
                    self._water_alarm_active[idx] = True
                    _mqtt_safe_publish(TOPIC_ALERT_WATER, f"START:{idx}")

            self._buzz_water_if_needed(now)

            if self.phase == "session":
                self.phase_remaining_sec = max(0, self.phase_remaining_sec - elapsed)
                self.total_remaining_sec = max(0, self.total_remaining_sec - elapsed)
                if self.phase_remaining_sec == 0:
                    if self._breaks_left > 0 and self.plan.break_length_min > 0:
                        self.phase = "break"
                        self.phase_remaining_sec = self.plan.break_length_min * 60
                        self._breaks_left -= 1
                        _mqtt_safe_publish(TOPIC_ALERT_BREAK, "START")
                    else:
                        if self.total_remaining_sec == 0:
                            self.running = False
                        else:
                            self.phase_remaining_sec = min(
                                self.plan.break_interval_min * 60, self.total_remaining_sec
                            )
                            self._next_session_cut += self.phase_remaining_sec
            else:
                self.phase_remaining_sec = max(0, self.phase_remaining_sec - elapsed)
                if self.phase_remaining_sec == 0:
                    _mqtt_safe_publish(TOPIC_ALERT_BREAK, "END")
                    if self.total_remaining_sec == 0:
                        self.running = False
                        self.phase = "session"
                    else:
                        self.phase = "session"
                        self.phase_remaining_sec = min(
                            self.plan.break_interval_min * 60, self.total_remaining_sec
                        )
                        self._next_session_cut += self.phase_remaining_sec

    def _buzz_water_if_needed(self, now: float):
        if any(self._water_alarm_active.values()) and (now - self._last_water_buzz >= 5.0):
            active_ids = [i for i, a in self._water_alarm_active.items() if a]
            _mqtt_safe_publish(TOPIC_ALERT_WATER, "PING:" + ",".join(map(str, active_ids)))
            self._last_water_buzz = now

    def snapshot(self):
        plan_dict = None
        if self.plan:
            plan_dict = {
                "duration_min": self.plan.duration_min,
                "break_interval_min": self.plan.break_interval_min,
                "break_count": self.plan.break_count,
                "break_length_min": self.plan.break_length_min,
                "water_amount_ml_per": self.plan.water_amount_ml_per,
                "water_total_ml": self.plan.water_total_ml,
                "water_milestones": self.plan.water_milestones
            }
        return {
            "running": self.running,
            "phase": self.phase,
            "phase_remaining_sec": self.phase_remaining_sec,
            "total_remaining_sec": self.total_remaining_sec,
            "plan": plan_dict,
            "water_active": self._water_alarm_active,
            "water_fired": self._water_fired
        }

scheduler = Scheduler()

# ============== MQTT HANDLERS ==============
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(TOPIC_STATUS)
        client.subscribe(TOPIC_DATA)
        client.subscribe(TOPIC_ALERT)
    else:
        print("MQTT connect failed:", rc)

def on_message(client, userdata, msg):
    global sensor_data, system_status
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
    try:
        c = mqtt.Client()
        c.on_connect = on_connect
        c.on_message = on_message
        c.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        c.loop_forever()
    except Exception as e:
        print("[WARNING] MQTT loop failed:", e)
        print("Running without hardware.")
        while True:
            time.sleep(10)

def _mqtt_safe_publish(topic: str, payload: str):
    try:
        c = mqtt.Client()
        c.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        c.loop_start()
        c.publish(topic, payload)
        c.loop_stop()
        c.disconnect()
    except Exception as e:
        print("[WARNING] MQTT publish failed:", topic, payload, "|", e)

# ============== BACKGROUND TICK ==============
def tick_loop():
    while True:
        scheduler.tick()
        time.sleep(1)

# ============== ROUTES ==============
@app.route("/")
def index():
    return render_template(
        "index.html",
        temp=sensor_data["temperature"],
        hum=sensor_data["humidity"],
        light=sensor_data["light"],
        status=system_status
    )

@app.route("/plan", methods=["POST"])
def route_plan():
    data = request.get_json(silent=True) or {}
    duration_min = int(data.get("duration_min", 60))
    plan = compute_plan(duration_min)
    return jsonify({
        "duration_min": plan.duration_min,
        "break_interval_min": plan.break_interval_min,
        "break_count": plan.break_count,
        "break_length_min": plan.break_length_min,
        "water_milestones": plan.water_milestones,
        "water_amount_ml_per": plan.water_amount_ml_per,
        "water_total_ml": plan.water_total_ml
    })

@app.route("/start", methods=["POST"])
def route_start():
    data = request.get_json(silent=True) or {}
    duration_min = int(data.get("duration_min", 60))
    plan = compute_plan(duration_min)

    scheduler.start(plan)
    _mqtt_safe_publish(TOPIC_CONFIG_DURATION, str(plan.duration_min))
    _mqtt_safe_publish(TOPIC_CONFIG_BREAK_INTERVAL, str(plan.break_interval_min))
    _mqtt_safe_publish(TOPIC_CONFIG_BREAK_LENGTH, str(plan.break_length_min))
    _mqtt_safe_publish(TOPIC_CONFIG_WATER_REMINDER, "on")
    _mqtt_safe_publish(TOPIC_CONTROL_START, "START")
    return jsonify({"ok": True})

@app.route("/stop", methods=["POST"])
def route_stop():
    scheduler.stop()
    _mqtt_safe_publish(TOPIC_CONTROL_STOP, "STOP")
    return jsonify({"ok": True})

@app.route("/reset", methods=["POST"])
def route_reset():
    scheduler.reset()
    _mqtt_safe_publish(TOPIC_CONTROL_RESET, "RESET")
    return jsonify({"ok": True})

@app.route("/water_ack", methods=["POST"])
def route_water_ack():
    data = request.get_json(silent=True) or {}
    milestone_id = int(data.get("milestone_id", -1))
    if milestone_id >= 0:
        scheduler.water_ack(milestone_id)
    return jsonify({"ok": True})

@app.route("/state", methods=["GET"])
def route_state():
    return jsonify(scheduler.snapshot())

@app.route("/status", methods=["GET"])
def route_status():
    # analisis kondisi ideal
    try:
        t = float(sensor_data["temperature"])
        h = float(sensor_data["humidity"])
        l = float(sensor_data["light"])
    except:
        t = h = l = None

    if t is None or h is None or l is None:
        condition = "Data tidak tersedia"
        alert_level = "unknown"
    else:
        issues = []
        if t < 22 or t > 30:
            issues.append("Suhu tidak ideal")
        if h < 40 or h > 70:
            issues.append("Kelembapan tidak ideal")
        if l < 200 or l > 800:
            issues.append("Pencahayaan tidak ideal")

        if len(issues) == 0:
            condition = "Kondisi ruangan ideal untuk belajar"
            alert_level = "good"
        else:
            condition = ", ".join(issues)
            alert_level = "bad"

    return jsonify({
        "system_status": condition,
        "temperature": sensor_data["temperature"],
        "humidity": sensor_data["humidity"],
        "light": sensor_data["light"],
        "alert_level": alert_level
    })

# ============== MAIN ==============
if __name__ == "__main__":
    threading.Thread(target=mqtt_loop, daemon=True).start()
    threading.Thread(target=tick_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=True)
