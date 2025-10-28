#!/usr/bin/env python3
"""
SWSC - Flask Backend with Robust MQTT (Fixed Disconnect Loop)
"""

import os
import sys
import time
import threading
import logging
import uuid
from dataclasses import dataclass
from typing import List, Dict, Optional

from flask import Flask, jsonify, render_template, request
import paho.mqtt.client as mqtt

# ============== LOGGING SETUP ==============
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============== MQTT CONFIG (FIXED) ==============
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 30  # ← Dikurangi dari 60 ke 30 detik
MQTT_RECONNECT_DELAY_MIN = 1
MQTT_RECONNECT_DELAY_MAX = 30

# Generate unique client ID with timestamp
MQTT_CLIENT_ID = f"SWSC_Flask_{uuid.uuid4().hex[:8]}_{int(time.time())}"

# Topics (unchanged)
TOPIC_CONFIG_DURATION = "swsc/config/duration"
TOPIC_CONFIG_BREAK_INTERVAL = "swsc/config/break_interval"
TOPIC_CONFIG_BREAK_LENGTH = "swsc/config/break_length"
TOPIC_CONFIG_WATER_REMINDER = "swsc/config/water_reminder"

TOPIC_CONTROL_START = "swsc/control/start"
TOPIC_CONTROL_STOP = "swsc/control/stop"
TOPIC_CONTROL_RESET = "swsc/control/reset"

TOPIC_ALERT_BREAK = "swsc/alert/break"
TOPIC_ALERT_WATER = "swsc/alert/water"

TOPIC_STATUS = "swsc/status/#"
TOPIC_DATA = "swsc/data/#"
TOPIC_ALERT = "swsc/alert/#"

# ============== FLASK APP ==============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=BASE_DIR,
    static_folder=BASE_DIR,
    static_url_path=""
)

# ============== GLOBAL STATE ==============
sensor_data_lock = threading.Lock()
sensor_data = {
    "temperature": "-",
    "humidity": "-",
    "light": "-"
}

system_status = "Disconnected"
mqtt_client = None
mqtt_connected = threading.Event()
mqtt_connection_count = 0

# ============== STUDY PLAN MODEL (UNCHANGED) ==============
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

# ============== SCHEDULER (UNCHANGED) ==============
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
        self._breaks_taken = 0
        self._water_alarm_active: Dict[int, bool] = {}
        self._water_fired: Dict[int, bool] = {}
        self._last_water_buzz = 0.0

    def start(self, plan: StudyPlan):
        with self.lock:
            logger.info(f"Starting session: {plan.duration_min} min, breaks every {plan.break_interval_min} min")
            self.plan = plan
            self.running = True
            self.phase = "session"
            self.total_remaining_sec = plan.duration_min * 60
            self._breaks_taken = 0
            if plan.break_count > 0:
                self.phase_remaining_sec = min(self.total_remaining_sec, plan.break_interval_min * 60)
            else:
                self.phase_remaining_sec = self.total_remaining_sec
            self._start_epoch = time.time()
            self._last_tick = self._start_epoch
            self._water_alarm_active = {i: False for i in range(len(plan.water_milestones))}
            self._water_fired = {i: False for i in range(len(plan.water_milestones))}
            self._last_water_buzz = 0.0
            logger.info("Session started successfully")

    def stop(self):
        with self.lock:
            if not self.running:
                return
            logger.info("Stopping session...")
            self.running = False
            self._start_epoch = None
            self._last_tick = None
            for i, active in list(self._water_alarm_active.items()):
                if active:
                    mqtt_publish(TOPIC_ALERT_WATER, f"STOP:{i}")
                    self._water_alarm_active[i] = False
            logger.info("Session stopped")

    def reset(self):
        with self.lock:
            logger.info("Resetting scheduler...")
            self.running = False
            self.phase = "session"
            self.phase_remaining_sec = 0
            self.total_remaining_sec = 0
            self.plan = None
            self._start_epoch = None
            self._last_tick = None
            self._breaks_taken = 0
            self._water_alarm_active.clear()
            self._water_fired.clear()
            self._last_water_buzz = 0.0
            logger.info("Scheduler reset complete")

    def water_ack(self, milestone_id: int):
        with self.lock:
            if self._water_alarm_active.get(milestone_id):
                logger.info(f"Water milestone {milestone_id} acknowledged")
                mqtt_publish(TOPIC_ALERT_WATER, f"STOP:{milestone_id}")
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
                    logger.info(f"Water milestone {idx} reached at {tsec}s")
                    self._water_fired[idx] = True
                    self._water_alarm_active[idx] = True
                    mqtt_publish(TOPIC_ALERT_WATER, f"START:{idx}")

            self._buzz_water_if_needed(now)

            if self.phase == "session":
                self.phase_remaining_sec = max(0, self.phase_remaining_sec - elapsed)
                self.total_remaining_sec = max(0, self.total_remaining_sec - elapsed)
                if self.phase_remaining_sec == 0:
                    if self._breaks_taken < self.plan.break_count and self.plan.break_length_min > 0:
                        logger.info(f"Break {self._breaks_taken + 1}/{self.plan.break_count} started")
                        self.phase = "break"
                        self.phase_remaining_sec = self.plan.break_length_min * 60
                        self._breaks_taken += 1
                        mqtt_publish(TOPIC_ALERT_BREAK, "START")
                    else:
                        if self.total_remaining_sec == 0:
                            logger.info("Session completed!")
                            self.running = False
                            mqtt_publish(TOPIC_CONTROL_STOP, "STOP", qos=1)
                        else:
                            self.phase_remaining_sec = min(self.plan.break_interval_min * 60, self.total_remaining_sec)
            elif self.phase == "break":
                self.phase_remaining_sec = max(0, self.phase_remaining_sec - elapsed)
                if self.phase_remaining_sec == 0:
                    logger.info("Break ended, resuming session")
                    mqtt_publish(TOPIC_ALERT_BREAK, "END")
                    if self.total_remaining_sec == 0:
                        self.running = False
                        self.phase = "session"
                        mqtt_publish(TOPIC_CONTROL_STOP, "STOP", qos=1)
                    else:
                        self.phase = "session"
                        self.phase_remaining_sec = min(self.plan.break_interval_min * 60, self.total_remaining_sec)

    def _buzz_water_if_needed(self, now: float):
        if any(self._water_alarm_active.values()) and (now - self._last_water_buzz >= 5.0):
            active_ids = [i for i, a in self._water_alarm_active.items() if a]
            mqtt_publish(TOPIC_ALERT_WATER, "PING:" + ",".join(map(str, active_ids)))
            self._last_water_buzz = now

    def snapshot(self):
        with self.lock:
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
                "water_active": dict(self._water_alarm_active),
                "water_fired": dict(self._water_fired)
            }

scheduler = Scheduler()

# ============== MQTT FUNCTIONS (FIXED) ==============

def mqtt_publish(topic: str, payload: str, qos: int = 1, retain: bool = False):
    """Publish with connection check and retry."""
    global mqtt_client
    
    if mqtt_client is None:
        logger.warning(f"MQTT client not initialized")
        return False
    
    # Wait max 2 seconds for connection
    if not mqtt_connected.wait(timeout=2):
        logger.warning(f"MQTT not connected, cannot publish: {topic}")
        return False
    
    try:
        result = mqtt_client.publish(topic, payload, qos=qos, retain=retain)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.debug(f"Published: {topic} = {payload}")
            return True
        else:
            logger.error(f"Publish failed: {topic}, rc={result.rc}")
            return False
    except Exception as e:
        logger.error(f"Publish exception: {topic} | {e}")
        return False

def on_connect(client, userdata, flags, rc):
    """MQTT connection callback (FIXED)."""
    global mqtt_connection_count
    mqtt_connection_count += 1
    
    if rc == 0:
        logger.info(f"MQTT connected successfully (connection #{mqtt_connection_count})")
        mqtt_connected.set()
        
        # Subscribe to topics with error handling
        try:
            client.subscribe(TOPIC_STATUS, qos=1)
            client.subscribe(TOPIC_DATA, qos=1)
            client.subscribe(TOPIC_ALERT, qos=1)
            logger.info("Subscribed to:")
            logger.info(f"  - {TOPIC_STATUS}")
            logger.info(f"  - {TOPIC_DATA}")
            logger.info(f"  - {TOPIC_ALERT}")
        except Exception as e:
            logger.error(f"Subscription failed: {e}")
    else:
        error_messages = {
            1: "Connection refused - incorrect protocol version",
            2: "Connection refused - invalid client identifier",
            3: "Connection refused - server unavailable",
            4: "Connection refused - bad username or password",
            5: "Connection refused - not authorized",
            7: "Network error or broker rate limit"
        }
        logger.error(f"MQTT connection failed: {error_messages.get(rc, f'Unknown error {rc}')}")
        mqtt_connected.clear()

def on_disconnect(client, userdata, rc):
    """MQTT disconnection callback (FIXED)."""
    logger.warning(f"MQTT disconnected (rc={rc})")
    mqtt_connected.clear()
    
    if rc == 0:
        logger.info("Clean disconnect")
    elif rc == 7:
        logger.warning("Network error or broker rate limit - will retry with backoff")
    else:
        logger.info(f"Unexpected disconnect (rc={rc}) - will auto-reconnect")

def on_message(client, userdata, msg):
    """MQTT message callback."""
    global sensor_data, system_status
    
    topic = msg.topic
    payload = msg.payload.decode("utf-8", errors="ignore")
    
    logger.debug(f"Received: {topic} = {payload}")
    
    if topic == "swsc/data/temperature":
        with sensor_data_lock:
            sensor_data["temperature"] = payload
    elif topic == "swsc/data/humidity":
        with sensor_data_lock:
            sensor_data["humidity"] = payload
    elif topic == "swsc/data/light":
        with sensor_data_lock:
            sensor_data["light"] = payload
    elif topic == "swsc/status/system":
        system_status = payload
        logger.info(f"System status: {system_status}")

def mqtt_loop():
    """MQTT network loop with exponential backoff (FIXED)."""
    global mqtt_client
    
    logger.info("Starting MQTT thread...")
    logger.info(f"Client ID: {MQTT_CLIENT_ID}")
    
    retry_delay = MQTT_RECONNECT_DELAY_MIN
    
    while True:
        try:
            # Create client with clean session
            mqtt_client = mqtt.Client(
                client_id=MQTT_CLIENT_ID,
                clean_session=True,
                protocol=mqtt.MQTTv311
            )
            
            mqtt_client.on_connect = on_connect
            mqtt_client.on_disconnect = on_disconnect
            mqtt_client.on_message = on_message
            
            # Configure socket timeout and keepalive
            mqtt_client._keepalive = MQTT_KEEPALIVE
            
            logger.info(f"Connecting to MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
            
            # Reset retry delay on successful connection
            retry_delay = MQTT_RECONNECT_DELAY_MIN
            
            # This blocks and processes network traffic
            mqtt_client.loop_forever()
            
        except KeyboardInterrupt:
            logger.info("MQTT loop interrupted by user")
            break
            
        except Exception as e:
            logger.error(f"MQTT loop error: {e}")
            mqtt_connected.clear()
            
            # Exponential backoff
            logger.info(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
            
            retry_delay = min(retry_delay * 2, MQTT_RECONNECT_DELAY_MAX)

def tick_loop():
    """Scheduler tick thread."""
    logger.info("Starting scheduler tick thread...")
    while True:
        try:
            scheduler.tick()
            time.sleep(1)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Tick loop error: {e}")

# ============== FLASK ROUTES (UNCHANGED) ==============

@app.route("/")
def index():
    with sensor_data_lock:
        return render_template(
            "index.html",
            temp=sensor_data["temperature"],
            hum=sensor_data["humidity"],
            light=sensor_data["light"],
            status=system_status
        )

@app.route("/plan", methods=["POST"])
def route_plan():
    try:
        data = request.get_json(silent=True) or {}
        duration_min = int(data.get("duration_min", 60))
        plan = compute_plan(duration_min)
        logger.info(f"Plan computed: {duration_min}min, {plan.break_count} breaks")
        return jsonify({
            "duration_min": plan.duration_min,
            "break_interval_min": plan.break_interval_min,
            "break_count": plan.break_count,
            "break_length_min": plan.break_length_min,
            "water_milestones": plan.water_milestones,
            "water_amount_ml_per": plan.water_amount_ml_per,
            "water_total_ml": plan.water_total_ml
        })
    except Exception as e:
        logger.error(f"Error in /plan: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/start", methods=["POST"])
def route_start():
    try:
        data = request.get_json(silent=True) or {}
        duration_min = int(data.get("duration_min", 60))
        
        plan = compute_plan(duration_min)
        scheduler.start(plan)
        
        # Wait for MQTT connection before sending config
        if not mqtt_connected.wait(timeout=5):
            logger.error("Cannot start - MQTT not connected")
            return jsonify({"error": "MQTT not connected"}), 503
        
        # Send configuration to ESP32
        mqtt_publish(TOPIC_CONFIG_DURATION, str(plan.duration_min), retain=True)
        time.sleep(0.1)
        mqtt_publish(TOPIC_CONFIG_BREAK_INTERVAL, str(plan.break_interval_min), retain=True)
        time.sleep(0.1)
        mqtt_publish(TOPIC_CONFIG_BREAK_LENGTH, str(plan.break_length_min), retain=True)
        time.sleep(0.1)
        mqtt_publish(TOPIC_CONFIG_WATER_REMINDER, "on", retain=True)
        time.sleep(0.2)
        
        # Send start command
        mqtt_publish(TOPIC_CONTROL_START, "START", qos=1)
        
        logger.info("Session start command sent")
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Error in /start: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/stop", methods=["POST"])
def route_stop():
    try:
        scheduler.stop()
        mqtt_publish(TOPIC_CONTROL_STOP, "STOP", qos=1)
        logger.info("Session stop command sent")
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Error in /stop: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/reset", methods=["POST"])
def route_reset():
    try:
        scheduler.reset()
        mqtt_publish(TOPIC_CONTROL_RESET, "RESET", qos=1)
        logger.info("Reset command sent")
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Error in /reset: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/water_ack", methods=["POST"])
def route_water_ack():
    try:
        data = request.get_json(silent=True) or {}
        milestone_id = int(data.get("milestone_id", -1))
        if milestone_id >= 0:
            scheduler.water_ack(milestone_id)
            logger.info(f"Water milestone {milestone_id} acknowledged")
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Error in /water_ack: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/state", methods=["GET"])
def route_state():
    try:
        return jsonify(scheduler.snapshot())
    except Exception as e:
        logger.error(f"Error in /state: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/status", methods=["GET"])
def route_status():
    try:
        with sensor_data_lock:
            temp_str = sensor_data["temperature"]
            hum_str = sensor_data["humidity"]
            light_str = sensor_data["light"]
        
        try:
            t = float(temp_str)
            h = float(hum_str)
            l = float(light_str)
        except:
            t = h = l = None
        
        if t is None or h is None or l is None:
            condition = "Sensor data unavailable"
            alert_level = "unknown"
        else:
            issues = []
            if t < 20 or t > 30:
                issues.append("Temperature")
            if h < 40 or h > 70:
                issues.append("Humidity")
            if l < 200 or l > 800:
                issues.append("Light")
            
            if len(issues) == 0:
                condition = "Environment is ideal for studying"
                alert_level = "good"
            else:
                condition = f"Check: {', '.join(issues)}"
                alert_level = "bad"
        
        return jsonify({
            "system_status": condition,
            "temperature": temp_str,
            "humidity": hum_str,
            "light": light_str,
            "alert_level": alert_level,
            "mqtt_connected": mqtt_connected.is_set()
        })
    except Exception as e:
        logger.error(f"Error in /status: {e}")
        return jsonify({"error": str(e)}), 500

# ============== MAIN ==============

def main():
    logger.info("═" * 60)
    logger.info("SWSC - Smart Wellness & Study Companion")
    logger.info("Flask Backend v2.1 (Fixed Disconnect Loop)")
    logger.info("═" * 60)
    
    # Start MQTT thread
    mqtt_thread = threading.Thread(target=mqtt_loop, daemon=True)
    mqtt_thread.start()
    logger.info("MQTT thread started")
    
    # Wait for MQTT connection
    logger.info("Waiting for MQTT connection (max 15s)...")
    connected = mqtt_connected.wait(timeout=15)
    
    if connected:
        logger.info("✓ MQTT connected successfully")
    else:
        logger.warning("✗ MQTT connection timeout")
        logger.warning("  Will continue trying in background...")
    
    # Start scheduler tick thread
    tick_thread = threading.Thread(target=tick_loop, daemon=True)
    tick_thread.start()
    logger.info("Scheduler thread started")
    
    logger.info("Starting Flask server on http://0.0.0.0:5000")
    logger.info("═" * 60)
    
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        logger.info("\nShutting down gracefully...")
        if mqtt_client:
            mqtt_client.disconnect()
            mqtt_client.loop_stop()
        logger.info("Goodbye!")

if __name__ == "__main__":
    main()