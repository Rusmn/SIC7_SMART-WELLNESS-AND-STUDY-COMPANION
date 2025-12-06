"""
Training script for environmental condition classifier.

Usage:
    python scripts/train_env_model.py --input data/raw/environment.csv --output models/environment.pkl --model rf
    python scripts/train_env_model.py --model extratrees
    python scripts/train_env_model.py --model xgb   # requires xgboost installed

Expected CSV columns: temperature, humidity, light, label
"""

import argparse
from pathlib import Path
from typing import Callable, Dict

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def load_dataset(path: Path) -> tuple[np.ndarray, np.ndarray]:
    df = pd.read_csv(path)
    required = {"temperature", "humidity", "light", "label"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in dataset: {missing}")
    X = df[["temperature", "humidity", "light"]].to_numpy()
    y = df["label"].astype(str).to_numpy()
    return X, y


def build_rf() -> Pipeline:
    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "clf",
                RandomForestClassifier(
                    n_estimators=180,
                    max_depth=None,
                    class_weight="balanced",
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def build_extratrees() -> Pipeline:
    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "clf",
                ExtraTreesClassifier(
                    n_estimators=200,
                    max_depth=None,
                    class_weight="balanced",
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def build_xgb() -> Pipeline:
    try:
        from xgboost import XGBClassifier
    except Exception as exc:  # noqa: BLE001
        raise ImportError("xgboost is not installed; install it to use --model xgb") from exc

    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "clf",
                XGBClassifier(
                    n_estimators=300,
                    max_depth=6,
                    learning_rate=0.1,
                    subsample=0.9,
                    colsample_bytree=0.9,
                    objective="multi:softprob",
                    eval_metric="mlogloss",
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )


MODEL_BUILDERS: Dict[str, Callable[[], Pipeline]] = {
    "rf": build_rf,
    "extratrees": build_extratrees,
    "xgb": build_xgb,
}


def train(input_path: Path, output_path: Path, model_name: str) -> None:
    X, y = load_dataset(input_path)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    builder = MODEL_BUILDERS[model_name]
    pipeline = builder()
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    report = classification_report(y_test, y_pred)
    print(f"Validation report ({model_name}):\n{report}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, output_path)
    print(f"Model saved to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train environment classifier.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/raw/environment.csv"),
        help="Path to labeled CSV (columns: temperature, humidity, light, label)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/environment.pkl"),
        help="Where to save the trained model",
    )
    parser.add_argument(
        "--model",
        choices=list(MODEL_BUILDERS.keys()),
        default="rf",
        help="Model type to train",
    )
    args = parser.parse_args()
    train(args.input, args.output, args.model)


if __name__ == "__main__":
    main()
