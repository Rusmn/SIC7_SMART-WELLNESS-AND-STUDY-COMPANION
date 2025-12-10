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
    CLOTHING_MAP = {
        'tipis': 0,
        'sedang': 1,
        'tebal': 2
    }

    def __init__(self, model_path: Path):
        self.model_path = model_path
        self.pipeline: Optional[Pipeline] = None

    def load_or_train(self) -> None:
        if self.model_path.exists():
            try:
                self.pipeline = joblib.load(self.model_path)
                logger.info(f"Environment model loaded from {self.model_path}")
                return
            except Exception as e:
                logger.warning(f"Failed to load existing model: {e}. Retraining...")

        logger.warning("Environment model not found or invalid. Training fallback synthetic model...")
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
            temp = float(sensor_data.get("temperature", 0))
            hum = float(sensor_data.get("humidity", 0))
            
            clothing_str = str(sensor_data.get("clothing", "sedang")).lower()
            clothing_val = self.CLOTHING_MAP.get(clothing_str, 1)

            x = np.array([temp, hum, float(clothing_val)]).reshape(1, -1)
            
        except Exception as exc: 
            logger.error(f"Invalid sensor data for prediction: {exc}")
            return None, 0.0

        proba = self.pipeline.predict_proba(x)[0]
        idx = int(np.argmax(proba))
        label = self.pipeline.classes_[idx]
        return str(label), float(proba[idx])

    def _train_synthetic(self) -> Pipeline:
        rng = np.random.default_rng(42)
        
        n = 1000
        t = rng.uniform(18, 35, n)
        h = rng.uniform(30, 90, n)
        l = rng.uniform(100, 800, n)
        c = rng.integers(0, 3, n)
        
        y = []
        for i in range(n):
            shift = 0
            if c[i] == 0: shift = 1.5
            if c[i] == 2: shift = -1.5
            
            opt_min, opt_max = 22.8 + shift, 25.8 + shift
            
            if (opt_min <= t[i] <= opt_max) and (40 <= h[i] <= 60):
                y.append("Nyaman")
            else:
                y.append("Tidak Nyaman")
                
        X = np.column_stack([t, h, l, c])
        y = np.array(y)

        pipeline = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                ("clf", RandomForestClassifier(n_estimators=100, random_state=42)),
            ]
        )
        pipeline.fit(X, y)
        return pipeline