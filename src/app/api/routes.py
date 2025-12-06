import csv
import io
import logging
import time
from collections import Counter
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

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
