import threading
import time
import uvicorn
import logging
from fastapi import FastAPI, Request, File, UploadFile, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.mqtt import (
    MQTTService, 
    TOPIC_CONFIG_DURATION, 
    TOPIC_CONFIG_BREAK_INTERVAL, 
    TOPIC_CONFIG_BREAK_LENGTH,
    TOPIC_CONFIG_WATER_REMINDER,
    TOPIC_CONTROL_START,
    TOPIC_CONTROL_STOP,
    TOPIC_CONTROL_RESET,
    TOPIC_ALERT_BREAK
)
from services.scheduler import Scheduler
from services.emotion import EmotionEngine

# Logging Setup
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger("main")

app = FastAPI()

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
templates = Jinja2Templates(directory="frontend")

mqtt = MQTTService()
scheduler = Scheduler(mqtt)
emotion = None

latest_emotion = {
    "label": "Menunggu...",
    "score": 0.0,
    "timestamp": 0
}
is_model_loading = True

def tick_loop():
    while True:
        try:
            scheduler.tick()
            time.sleep(0.1) 
        except Exception as e:
            logger.error(f"Tick loop error: {e}")

def load_model_background():
    global emotion, is_model_loading
    logger.info("⏳ Memulai download/loading Model AI di background...")
    try:
        emotion = EmotionEngine()
        is_model_loading = False
        logger.info("✅ Model AI SIAP digunakan!")
    except Exception as e:
        logger.error(f"❌ Gagal load model: {e}")

@app.on_event("startup")
async def startup():
    mqtt.start()
    
    logger.info("Waiting for MQTT connection...")
    mqtt.connected_event.wait(timeout=2) 
    
    threading.Thread(target=load_model_background, daemon=True).start()
    
    threading.Thread(target=tick_loop, daemon=True).start()

@app.on_event("shutdown")
async def shutdown():
    mqtt.stop()

# --- Routes ---

@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "temp": mqtt.sensor_data["temperature"],
        "hum": mqtt.sensor_data["humidity"],
        "light": mqtt.sensor_data["light"],
        "status": mqtt.system_status
    })

class PlanReq(BaseModel):
    duration_min: int

class AckRequest(BaseModel):
    milestone_id: int

@app.post("/plan")
def compute_plan(req: PlanReq):
    return scheduler.compute_plan(req.duration_min)

@app.post("/start")
def start(req: PlanReq):
    plan = scheduler.compute_plan(req.duration_min)
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

@app.post("/stop")
def stop():
    scheduler.stop()
    mqtt.publish(TOPIC_CONTROL_STOP, "STOP", qos=1)
    return {"ok": True}

@app.post("/reset")
def reset():
    scheduler.reset()
    mqtt.publish(TOPIC_CONTROL_RESET, "RESET", qos=1)
    return {"ok": True}

@app.post("/water_ack")
def ack_water(req: AckRequest):
    scheduler.ack_water(req.milestone_id)
    return {"ok": True}

@app.get("/status")
def get_status():
    data = mqtt.sensor_data
    try:
        t = float(data["temperature"])
        h = float(data["humidity"])
        l = float(data["light"])
        
        issues = []
        if t < 20 or t > 30: issues.append("Temperature")
        if h < 40 or h > 70: issues.append("Humidity")
        if l == 0: issues.append("Light (Too Dark)")
        
        if len(issues) == 0:
            cond = "Environment is ideal for studying"
            alert = "good"
        else:
            cond = f"Check: {', '.join(issues)}"
            alert = "bad"
    except:
        cond = "Sensor data unavailable"
        alert = "unknown"

    return {
        "sensor": data,
        "status": cond,
        "alert_level": alert,
        "scheduler": scheduler.snapshot(),
        "emotion": latest_emotion,
        "mqtt_connected": mqtt.connected_event.is_set()
    }

@app.post("/camera/analyze")
async def camera_analyze(file: UploadFile = File(...)):
    global latest_emotion
    try:
        img = await file.read()
        label, score = emotion.predict(img)
        
        if label:
            latest_emotion = {
                "label": label,
                "score": float(score),
                "timestamp": time.time()
            }

        action = "NONE"
        if label in ["sad", "angry", "fear", "disgust"] and score > 0.5:
            mqtt.publish(TOPIC_ALERT_BREAK, "START")
            action = "TRIGGER_BREAK"

        return {"emotion": label, "score": score, "action": action}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)