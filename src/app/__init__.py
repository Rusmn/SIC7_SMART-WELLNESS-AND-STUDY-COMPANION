import logging
from pathlib import Path

from fastapi import FastAPI

from app.api.routes import router
from app.core.environment_classifier import EnvironmentClassifier
from app.core.mqtt import MQTTService
from app.core.scheduler import Scheduler
from app.lifecycle import register_events

# Configure base logging once so uvicorn picks it up too.
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger("main")


def create_app() -> FastAPI:
    app = FastAPI(title="SWSC API", docs_url="/docs", redoc_url=None)

    mqtt_service = MQTTService()
    scheduler = Scheduler(mqtt_service)
    env_classifier = EnvironmentClassifier(
        model_path=Path(__file__).resolve().parent.parent / "models" / "environment.pkl"
    )

    app.state.mqtt = mqtt_service
    app.state.scheduler = scheduler
    app.state.env_classifier = env_classifier
    app.state.emotion = None
    app.state.latest_emotion = {
        "label": "Menunggu...",
        "score": 0.0,
        "timestamp": 0,
    }
    app.state.emotion_history = []  # List of emotion records during session
    app.state.session_start_time = 0  # Track when session starts
    app.state.is_model_loading = True
    app.state.clothing = {
        "insulation": 1.0,  # 0=tipis, 1=sedang, 2=tebal
        "source": "default",
        "updated_at": 0.0,
    }

    app.include_router(router)
    register_events(app)

    return app


__all__ = ["create_app"]
