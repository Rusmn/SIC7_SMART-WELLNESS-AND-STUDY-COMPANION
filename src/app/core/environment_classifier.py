import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger("uvicorn")


class EnvironmentClassifier:
    """
    Wrapper for sensor-based classifier.
    Uses RandomForest for better nonlinear separation; falls back to a synthetic model if none exists.
    """

    def __init__(self, model_path: Path):
        self.model_path = model_path
        self.pipeline: Optional[Pipeline] = None

    def load_or_train(self) -> None:
        if self.model_path.exists():
            self.pipeline = joblib.load(self.model_path)
            logger.info(f"Environment model loaded from {self.model_path}")
            return

        logger.warning("Environment model not found. Training fallback synthetic model...")
        self.pipeline = self._train_synthetic()
        self.save()
        logger.info("Fallback environment model trained and saved.")

    def save(self) -> None:
        if self.pipeline is None:
            logger.warning("Cannot save environment model: pipeline is None")
            return
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.pipeline, self.model_path)

    def predict(self, sensor_data: Dict[str, str]) -> Tuple[Optional[str], float]:
        if self.pipeline is None:
            return None, 0.0

        try:
            x = np.array(
                [
                    float(sensor_data.get("temperature", 0)),
                    float(sensor_data.get("humidity", 0)),
                    float(sensor_data.get("light", 0)),
                ]
            ).reshape(1, -1)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Invalid sensor data for prediction: {exc}")
            return None, 0.0

        proba = self.pipeline.predict_proba(x)[0]
        idx = int(np.argmax(proba))
        label = self.pipeline.classes_[idx]
        return str(label), float(proba[idx])

    def _train_synthetic(self) -> Pipeline:
        rng = np.random.default_rng(42)

        def block(mean_temp, mean_hum, mean_light, label, n=80):
            t = rng.normal(mean_temp, 1.8, n)
            h = rng.normal(mean_hum, 5.0, n)
            l = rng.normal(mean_light, 20.0, n)
            y = np.full(n, label)
            return np.column_stack([t, h, l]), y

        xs, ys = [], []
        for mean_t, mean_h, mean_l, lbl in [
            (25, 55, 150, "nyaman"),
            (32, 35, 140, "panas_kering"),
            (24, 80, 130, "lembap"),
            (23, 60, 10, "gelap"),
        ]:
            x, y = block(mean_t, mean_h, mean_l, lbl)
            xs.append(x)
            ys.append(y)

        X = np.vstack(xs)
        y = np.concatenate(ys)

        pipeline = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                ("clf", RandomForestClassifier(
                    n_estimators=120,
                    max_depth=None,
                    class_weight="balanced",
                    random_state=42,
                    n_jobs=-1,
                )),
            ]
        )
        pipeline.fit(X, y)
        return pipeline
