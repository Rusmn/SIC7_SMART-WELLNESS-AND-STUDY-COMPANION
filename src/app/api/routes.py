import csv
import io
import asyncio
import json
import logging
import time
from collections import Counter
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, WebSocket
from fastapi.responses import StreamingResponse

from app.api.models import AckRequest, ClothingRequest, PlanRequest
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


def _build_status_payload(
    app_state,
    simulate: bool = False,
    temp: Optional[float] = None,
    hum: Optional[float] = None,
    clothing_insulation: Optional[float] = None,
    light: Optional[float] = None,
):
    scheduler: Scheduler = app_state.scheduler
    mqtt: MQTTService = app_state.mqtt
    latest_emotion = app_state.latest_emotion
    env_classifier: EnvironmentClassifier = app_state.env_classifier
    clothing_state = app_state.clothing

    if simulate:
        data = {
            "temperature": temp if temp is not None else 25.0,
            "humidity": hum if hum is not None else 60.0,
            "light": light if light is not None else 150.0,
        }
        mqtt_connected = False
    else:
        data = mqtt.sensor_data
        mqtt_connected = mqtt.connected_event.is_set()

    try:
        light_value = float(data.get("light", 0) or 0)
    except Exception:
        light_value = 0.0

    clothing_value = clothing_insulation
    if clothing_value is None:
        clothing_value = float(clothing_state.get("insulation", 1.0))

    clothing_info = clothing_state.copy()
    if simulate:
        clothing_info = {
            "insulation": clothing_value,
            "source": "simulate",
            "updated_at": time.time(),
        }

    if light_value == 0.0:
        cond = "gelap"
        conf = 1.0
        alert = "tidak_ideal"
    else:
        label, conf = env_classifier.predict(data, clothing_value)
        if label:
            cond = str(label)
            good_labels = {"nyaman", "aman", "ideal", "normal"}
            if cond.lower() in good_labels and conf >= 0.6:
                alert = "ideal"
            elif cond.lower() in good_labels and conf >= 0.3:
                alert = "kurang_ideal"
            else:
                alert = "tidak_ideal"
        else:
            cond = "Model not ready"
            alert = "tidak_ideal"

    return {
        "sensor": data,
        "status": cond,
        "alert_level": alert,
        "scheduler": scheduler.snapshot(),
        "emotion": latest_emotion,
        "env_prediction": {"label": cond, "confidence": conf},
        "mqtt_connected": mqtt_connected,
        "clothing": clothing_info,
        "simulate": simulate,
    }


@router.get("/")
def index():
    return {"message": "SWSC API is running. Use /status or the Streamlit dashboard."}


@router.post("/plan")
def compute_plan(req: PlanRequest):
    return scheduler_module.compute_plan(req.duration_min)


@router.post("/start")
def start(req: PlanRequest, request: Request):
    scheduler: Scheduler = request.app.state.scheduler
    mqtt: MQTTService = request.app.state.mqtt

    plan = scheduler_module.compute_plan(req.duration_min)
    scheduler.start(plan)

    # Reset emotion history for new session and mark start time
    request.app.state.emotion_history = []
    request.app.state.session_start_time = time.time()

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
    scheduler.water_ack(req.milestone_id)
    return {"ok": True}


@router.get("/status")
def get_status(
    request: Request,
    simulate: bool = Query(False, description="Gunakan data simulasi, bukan MQTT"),
    temp: Optional[float] = Query(None, alias="temperature"),
    hum: Optional[float] = Query(None, alias="humidity"),
    clothing_insulation: Optional[float] = Query(None),
    light: Optional[float] = Query(None),
):
    return _build_status_payload(request.app.state, simulate, temp, hum, clothing_insulation, light)


@router.post("/clothing")
def set_clothing(req: ClothingRequest, request: Request):
    clothing_state = request.app.state.clothing
    clothing_state["insulation"] = float(req.insulation)
    clothing_state["source"] = "manual"
    clothing_state["updated_at"] = time.time()
    return {"ok": True, "clothing": clothing_state}


@router.get("/clothing")
def get_clothing(request: Request):
    return request.app.state.clothing


@router.websocket("/ws/status")
async def ws_status(
    websocket: WebSocket,
    simulate: bool = False,
    temperature: Optional[float] = None,
    humidity: Optional[float] = None,
    clothing_insulation: Optional[float] = None,
    light: Optional[float] = None,
):
    await websocket.accept()
    try:
        while True:
            payload = _build_status_payload(
                app_state=websocket.app.state,
                simulate=simulate,
                temp=temperature,
                hum=humidity,
                clothing_insulation=clothing_insulation,
                light=light,
            )
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1)
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/emotion")
async def ws_emotion(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            latest = websocket.app.state.latest_emotion  # type: ignore[attr-defined]
            await websocket.send_text(json.dumps(latest))
            await asyncio.sleep(1)
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass


@router.get("/emotion/summary")
def get_emotion_summary(request: Request):
    """Get emotion statistics from the current/last session."""
    history = request.app.state.emotion_history
    session_start = request.app.state.session_start_time

    if not history:
        return {
            "total_records": 0,
            "most_frequent": None,
            "emotion_counts": {},
            "emotion_percentages": {},
            "average_confidence": 0.0,
        }

    # Filter only emotions from current session (if session_start is set)
    if session_start > 0:
        history = [r for r in history if r["timestamp"] >= session_start]

    if not history:
        return {
            "total_records": 0,
            "most_frequent": None,
            "emotion_counts": {},
            "emotion_percentages": {},
            "average_confidence": 0.0,
        }

    # Count emotions
    emotion_labels = [record["label"] for record in history]
    emotion_counts = Counter(emotion_labels)
    total = len(emotion_labels)

    # Calculate percentages
    emotion_percentages = {
        label: round((count / total) * 100, 2)
        for label, count in emotion_counts.items()
    }

    # Most frequent emotion
    most_frequent = emotion_counts.most_common(1)[0] if emotion_counts else (None, 0)

    # Average confidence
    avg_confidence = sum(record["score"] for record in history) / total if total > 0 else 0.0

    return {
        "total_records": total,
        "most_frequent": {
            "label": most_frequent[0],
            "count": most_frequent[1],
            "percentage": emotion_percentages.get(most_frequent[0], 0.0),
        },
        "emotion_counts": dict(emotion_counts),
        "emotion_percentages": emotion_percentages,
        "average_confidence": round(avg_confidence, 4),
    }


@router.get("/emotion/export")
def export_emotion_csv(request: Request):
    """Export emotion history as CSV file."""
    history = request.app.state.emotion_history
    session_start = request.app.state.session_start_time

    # Filter only emotions from current session
    if session_start > 0:
        history = [r for r in history if r["timestamp"] >= session_start]

    if not history:
        raise HTTPException(status_code=404, detail="No emotion data to export")

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(["Timestamp", "DateTime", "Emotion", "Confidence", "Confidence %"])

    # Write data
    for record in history:
        timestamp = record["timestamp"]
        dt = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        label = record["label"]
        score = record["score"]
        score_pct = f"{score * 100:.2f}%"

        writer.writerow([timestamp, dt, label, score, score_pct])

    # Prepare response
    output.seek(0)
    filename = f"emotion_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/camera/analyze")
async def camera_analyze(request: Request, file: UploadFile = File(...)):
    latest_emotion = request.app.state.latest_emotion
    mqtt: MQTTService = request.app.state.mqtt
    emotion: Optional[EmotionEngine] = request.app.state.emotion
    scheduler: Scheduler = request.app.state.scheduler

    try:
        if emotion is None:
            raise HTTPException(status_code=503, detail="Emotion model not ready")

        img = await file.read()
        label, score = emotion.predict(img)

        if label:
            timestamp = time.time()
            latest_emotion = {
                "label": label,
                "score": float(score),
                "timestamp": timestamp,
            }
            request.app.state.latest_emotion = latest_emotion

            # Save to history if session is running
            if scheduler.running:
                request.app.state.emotion_history.append({
                    "label": label,
                    "score": float(score),
                    "timestamp": timestamp,
                })

        action = "NONE"
        if label in ["sad", "angry", "fear", "disgust"] and score > 0.5:
            mqtt.publish(TOPIC_ALERT_BREAK, "START")
            action = "TRIGGER_BREAK"

        return {"emotion": latest_emotion, "action": action}
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Camera analyze error: {exc}")
        return {"error": str(exc)}
