import logging
import time
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.api.models import AckRequest, PlanRequest
from app.core import scheduler as scheduler_module
from app.core.emotion import EmotionEngine
from app.core.environment_classifier import EnvironmentClassifier
from app.core.mqtt import (
    MQTTService,
    TOPIC_ALERT_BREAK,
    TOPIC_ALERT_WATER,
    TOPIC_CONFIG_BREAK_INTERVAL,
    TOPIC_CONFIG_BREAK_LENGTH,
    TOPIC_CONFIG_DURATION,
    TOPIC_CONFIG_WATER_REMINDER,
    TOPIC_CONTROL_RESET,
    TOPIC_CONTROL_START,
    TOPIC_CONTROL_STOP,
)
from app.core.scheduler import Scheduler

router = APIRouter()
logger = logging.getLogger("main")


@router.get("/")
def index(request: Request):
    mqtt: MQTTService = request.app.state.mqtt
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "temp": mqtt.sensor_data["temperature"],
            "hum": mqtt.sensor_data["humidity"],
            "light": mqtt.sensor_data["light"],
            "status": mqtt.system_status,
        },
    )


@router.post("/plan")
def compute_plan(req: PlanRequest):
    return scheduler_module.compute_plan(req.duration_min)


@router.post("/start")
def start(req: PlanRequest, request: Request):
    scheduler: Scheduler = request.app.state.scheduler
    mqtt: MQTTService = request.app.state.mqtt

    plan = scheduler_module.compute_plan(req.duration_min)
    scheduler.start(plan)

    if not mqtt.connected_event.is_set():
        raise HTTPException(status_code=503, detail="MQTT not connected")

    mqtt.publish(TOPIC_CONFIG_DURATION, str(plan.duration_min), retain=True)
    time.sleep(0.1)
    mqtt.publish(TOPIC_CONFIG_BREAK_INTERVAL, str(plan.break_interval_min), retain=True)
    time.sleep(0.1)
    mqtt.publish(TOPIC_CONFIG_BREAK_LENGTH, str(plan.break_length_min), retain=True)
    time.sleep(0.1)
    mqtt.publish(TOPIC_CONFIG_WATER_REMINDER, "on", retain=True)
    time.sleep(0.2)

    mqtt.publish(TOPIC_CONTROL_START, "START", qos=1)
    return {"ok": True}


@router.post("/stop")
def stop(request: Request):
    scheduler: Scheduler = request.app.state.scheduler
    mqtt: MQTTService = request.app.state.mqtt

    scheduler.stop()
    mqtt.publish(TOPIC_CONTROL_STOP, "STOP", qos=1)
    return {"ok": True}


@router.post("/reset")
def reset(request: Request):
    scheduler: Scheduler = request.app.state.scheduler
    mqtt: MQTTService = request.app.state.mqtt

    scheduler.reset()
    mqtt.publish(TOPIC_CONTROL_RESET, "RESET", qos=1)
    return {"ok": True}


@router.post("/water_ack")
def ack_water(req: AckRequest, request: Request):
    scheduler: Scheduler = request.app.state.scheduler
    scheduler.ack_water(req.milestone_id)
    return {"ok": True}


@router.get("/status")
def get_status(request: Request):
    scheduler: Scheduler = request.app.state.scheduler
    mqtt: MQTTService = request.app.state.mqtt
    latest_emotion = request.app.state.latest_emotion
    env_classifier: EnvironmentClassifier = request.app.state.env_classifier

    data = mqtt.sensor_data
    label, conf = env_classifier.predict(data)
    if label:
        cond = label
        good_labels = {"nyaman", "aman", "ideal", "normal"}
        alert = "good" if label.lower() in good_labels and conf >= 0.5 else "bad"
    else:
        cond = "Model not ready"
        alert = "unknown"

    return {
        "sensor": data,
        "status": cond,
        "alert_level": alert,
        "scheduler": scheduler.snapshot(),
        "emotion": latest_emotion,
        "env_prediction": {"label": cond, "confidence": conf},
        "mqtt_connected": mqtt.connected_event.is_set(),
    }


@router.post("/camera/analyze")
async def camera_analyze(request: Request, file: UploadFile = File(...)):
    latest_emotion = request.app.state.latest_emotion
    mqtt: MQTTService = request.app.state.mqtt
    emotion: Optional[EmotionEngine] = request.app.state.emotion

    try:
        if emotion is None:
            raise HTTPException(status_code=503, detail="Emotion model not ready")

        img = await file.read()
        label, score = emotion.predict(img)

        if label:
            latest_emotion = {
                "label": label,
                "score": float(score),
                "timestamp": time.time(),
            }
            request.app.state.latest_emotion = latest_emotion

        action = "NONE"
        if label in ["sad", "angry", "fear", "disgust"] and score > 0.5:
            mqtt.publish(TOPIC_ALERT_BREAK, "START")
            action = "TRIGGER_BREAK"

        return {"emotion": label, "score": score, "action": action}
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Camera analyze error: {exc}")
        return {"error": str(exc)}
