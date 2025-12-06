import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import router
from app.core.environment_classifier import EnvironmentClassifier
from app.core.mqtt import MQTTService
from app.core.scheduler import Scheduler
from app.lifecycle import register_events

# Configure base logging once so uvicorn picks it up too.
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger("main")

WEB_DIR = Path(__file__).resolve().parent / "web"


def create_app() -> FastAPI:
    app = FastAPI()

    static_dir = WEB_DIR / "static"
    templates_dir = WEB_DIR / "templates"

    app.mount("/frontend", StaticFiles(directory=static_dir), name="frontend")
    app.state.templates = Jinja2Templates(directory=templates_dir)

    mqtt_service = MQTTService()
    scheduler = Scheduler(mqtt_service)
    env_classifier = EnvironmentClassifier(model_path=Path(__file__).resolve().parent.parent / "models" / "environment.pkl")

    app.state.mqtt = mqtt_service
    app.state.scheduler = scheduler
    app.state.env_classifier = env_classifier
    app.state.emotion = None
    app.state.latest_emotion = {
        "label": "Menunggu...",
        "score": 0.0,
        "timestamp": 0,
    }
    app.state.is_model_loading = True

    app.include_router(router)
    register_events(app)

    return app


__all__ = ["create_app", "WEB_DIR"]
