import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.core.mqtt import TOPIC_ALERT_BREAK, TOPIC_ALERT_WATER, TOPIC_ALERT_ENV, TOPIC_CONTROL_STOP, TOPIC_ALERT_FINISHED

# Gunakan logger uvicorn agar tampil di konsol FastAPI
logger = logging.getLogger("uvicorn")

@dataclass
class StudyPlan:
    duration_min: int
    break_interval_min: int
    break_count: int
    break_length_min: int
    water_milestones: List[int]
    water_ml: int
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
        water_ml=per_ml,
        water_total_ml=total_ml
    )

class Scheduler:
    def __init__(self, mqtt_service):
        self.mqtt = mqtt_service 
        
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
        self.current_env_status = "ideal"
        self._last_env_buzz = 0
        self._is_env_buzzing = False

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
            self.phase = "session"
            self.phase_remaining_sec = 0
            self.total_remaining_sec = 0
            self._start_epoch = None
            self._last_tick = None
            for i, active in list(self._water_alarm_active.items()):
                if active:
                    self.mqtt.publish(TOPIC_ALERT_WATER, f"STOP:{i}")
                    self._water_alarm_active[i] = False
            self._water_alarm_active.clear()
            self._water_fired.clear()
            try:
                self.mqtt.publish(TOPIC_CONTROL_STOP, "STOP", qos=1)
            except Exception:
                pass
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
                self.mqtt.publish(TOPIC_ALERT_WATER, f"STOP:{milestone_id}")
                self._water_alarm_active[milestone_id] = False

    def tick(self):
        with self.lock:
            if not self.running or self.plan is None or self._last_tick is None:
                return
            
            now = time.time()
            
            if self.current_env_status == "tidak_ideal":
                if now - self._last_env_buzz >= 2.0:
                    self.mqtt.publish(TOPIC_ALERT_ENV, "WARNING")
                    self._last_env_buzz = now
            
            elif self.current_env_status == "kurang_ideal":
                if now - self._last_env_buzz >= 15.0:
                    self.mqtt.publish(TOPIC_ALERT_ENV, "WARNING")
                    self._last_env_buzz = now
                    
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
                    self._last_water_buzz = now
                    self.mqtt.publish(TOPIC_ALERT_WATER, f"START:{idx}")

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
                        self.mqtt.publish(TOPIC_ALERT_BREAK, "START")
                    else:
                        if self.total_remaining_sec == 0:
                            logger.info("Session completed!")
                            self.running = False
                            self.phase = "completed"
                            self.mqtt.publish(TOPIC_ALERT_FINISHED, "Session Completed")
                            self.mqtt.publish(TOPIC_CONTROL_STOP, "STOP", qos=1)
                        else:
                            self.phase_remaining_sec = min(self.plan.break_interval_min * 60, self.total_remaining_sec)
            elif self.phase == "break":
                self.phase_remaining_sec = max(0, self.phase_remaining_sec - elapsed)
                if self.phase_remaining_sec == 0:
                    logger.info("Break ended, resuming session")
                    self.mqtt.publish(TOPIC_ALERT_BREAK, "END")
                    if self.total_remaining_sec == 0:
                        self.running = False
                        self.phase = "session"
                        self.phase = "completed"
                        self.mqtt.publish(TOPIC_ALERT_FINISHED, "Session Completed")
                        self.mqtt.publish(TOPIC_CONTROL_STOP, "STOP", qos=1)
                    else:
                        self.phase = "session"
                        self.phase_remaining_sec = min(self.plan.break_interval_min * 60, self.total_remaining_sec)

    def _buzz_water_if_needed(self, now: float):
        if any(self._water_alarm_active.values()) and (now - self._last_water_buzz >= 0.5):
            active_ids = [i for i, a in self._water_alarm_active.items() if a]
            if active_ids:
                payload = "PING:" + ",".join(map(str, active_ids))
                self.mqtt.publish(TOPIC_ALERT_WATER, payload)
                self._last_water_buzz = now
    
    def set_env_status(self, status: str):
        self.current_env_status = status

    def snapshot(self):
        with self.lock:
            plan_dict = None
            if self.plan:
                plan_dict = {
                    "duration_min": self.plan.duration_min,
                    "break_interval_min": self.plan.break_interval_min,
                    "break_count": self.plan.break_count,
                    "break_length_min": self.plan.break_length_min,
                    "water_ml": self.plan.water_ml,
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
