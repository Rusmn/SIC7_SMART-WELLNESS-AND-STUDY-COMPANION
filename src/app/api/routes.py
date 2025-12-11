import csv
import io
import asyncio
import json
import logging
import time
from collections import Counter
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.api.models import AckRequest, PlanRequest
from app.core import scheduler as scheduler_module
from app.core.emotion import EmotionEngine
from app.core.clothing import ClothingEngine
from app.core.environment_classifier import EnvironmentClassifier
from app.core.mqtt import (
    MQTTService,
    TOPIC_ALERT_BREAK,
    TOPIC_ALERT_WATER,
    TOPIC_ALERT_ENV,
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
    
    latest_clothing_label = getattr(app_state, "latest_clothing", "Sedang")

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

    clothing_map = {"tipis": 0, "sedang": 1, "tebal": 2}
    current_clothing_val = clothing_map.get(str(latest_clothing_label).lower(), 1)

    clothing_value = clothing_insulation
    if clothing_value is None:
        clothing_value = float(current_clothing_val)

    clothing_info = {
        "insulation": clothing_value,
        "label": str(latest_clothing_label),
        "source": "simulate" if simulate else "camera",
        "updated_at": time.time(),
    }

    if light_value == 0.0:
        cond = "gelap"
        conf = 1.0
        alert = "tidak_ideal"
    else:
        label, conf = env_classifier.predict(data)
        if label:
            cond = str(label)
            alert = "ideal" if label == "Ideal" else "kurang_ideal" if label == "Kurang Ideal" else "tidak_ideal"
        else:
            cond = "Model not ready"
            alert = "tidak_ideal"

    scheduler.set_env_status(alert)
    
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
    simulate: bool = False,
    temperature: Optional[float] = None,
    humidity: Optional[float] = None,
    clothing_insulation: Optional[float] = None,
    light: Optional[float] = None
):
    return _build_status_payload(
        app_state=request.app.state,
        simulate=simulate,
        temp=temperature,
        hum=humidity,
        clothing_insulation=clothing_insulation,
        light=light
    )


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()


@router.websocket("/ws/status")
async def ws_status(
    websocket: WebSocket,
    simulate: bool = False,
    temperature: Optional[float] = None,
    humidity: Optional[float] = None,
    clothing_insulation: Optional[float] = None,
    light: Optional[float] = None,
):
    await manager.connect(websocket)
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
        pass
    finally:
        manager.disconnect(websocket)


@router.websocket("/ws/emotion")
async def ws_emotion(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            latest = websocket.app.state.latest_emotion
            await websocket.send_text(json.dumps(latest))
            await asyncio.sleep(1)
    except Exception:
        pass
    finally:
        manager.disconnect(websocket)


@router.get("/emotion/summary")
def get_emotion_summary(request: Request):
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

    emotion_labels = [record["label"] for record in history]
    emotion_counts = Counter(emotion_labels)
    total = len(emotion_labels)

    emotion_percentages = {
        label: round((count / total) * 100, 2)
        for label, count in emotion_counts.items()
    }

    most_frequent = emotion_counts.most_common(1)[0] if emotion_counts else (None, 0)

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
    history = request.app.state.emotion_history
    session_start = request.app.state.session_start_time

    if session_start > 0:
        history = [r for r in history if r["timestamp"] >= session_start]

    if not history:
        raise HTTPException(status_code=404, detail="No emotion data to export")

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Timestamp", "DateTime", "Emotion", "Confidence", "Confidence %"])

    for record in history:
        timestamp = record["timestamp"]
        dt = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        label = record["label"]
        score = record["score"]
        score_pct = f"{score * 100:.2f}%"

        writer.writerow([timestamp, dt, label, score, score_pct])

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
    clothing: Optional[ClothingEngine] = request.app.state.clothing
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

            if scheduler.running:
                request.app.state.emotion_history.append({
                    "label": label,
                    "score": float(score),
                    "timestamp": timestamp,
                })
            
            await manager.broadcast(latest_emotion)

        if clothing:
            clothing_label = clothing.predict(img)
            request.app.state.latest_clothing = clothing_label

        action = "NONE"
        if label in ["sad", "angry", "fear", "disgust"] and score > 0.5:
            # mqtt.publish(TOPIC_ALERT_BREAK, "START")
            # action = "TRIGGER_BREAK"
            pass

        return {
            "emotion": latest_emotion, 
            "clothing": request.app.state.latest_clothing,
            "action": action
        }
    except Exception as exc:
        logger.error(f"Camera analyze error: {exc}")
        return {"error": str(exc)}