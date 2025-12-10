import logging
import threading
import time

from fastapi import FastAPI

from app.core.emotion import EmotionEngine
from app.core.clothing import ClothingEngine
from app.core.environment_classifier import EnvironmentClassifier

logger = logging.getLogger("main")

def _tick_loop(app: FastAPI) -> None:
    scheduler = app.state.scheduler
    interval = 0.1
    next_tick = time.monotonic()
    while True:
        try:
            scheduler.tick()
        except Exception as exc:
            logger.error(f"Tick loop error: {exc}")
        next_tick += interval
        sleep_for = max(0.0, next_tick - time.monotonic())
        if sleep_for:
            time.sleep(sleep_for)
        else:
            next_tick = time.monotonic()

def _load_model_background(app: FastAPI) -> None:
    logger.info("⏳ Memulai download/loading Model AI di background...")
    try:
        app.state.emotion = EmotionEngine()
        app.state.clothing = ClothingEngine()
        app.state.is_model_loading = False
        logger.info("✅ Model AI (Emotion & Clothing) SIAP digunakan!")
    except Exception as exc:
        logger.error(f"❌ Gagal load model: {exc}")

def register_events(app: FastAPI) -> None:
    @app.on_event("startup")
    async def _startup() -> None:
        mqtt = app.state.mqtt
        env_classifier: EnvironmentClassifier = app.state.env_classifier

        mqtt.start()
        logger.info("Waiting for MQTT connection...")
        mqtt.connected_event.wait(timeout=2)

        try:
            env_classifier.load_or_train()
        except Exception as exc:
            logger.error(f"Gagal memuat model lingkungan: {exc}")

        threading.Thread(target=_load_model_background, args=(app,), daemon=True).start()
        threading.Thread(target=_tick_loop, args=(app,), daemon=True).start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        app.state.mqtt.stop()