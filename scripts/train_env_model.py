"""
Compatibility wrapper for training the environment model.

This delegates to `app.training.env_model` so all logic lives under `src/`.
Usage remains the same:
    python scripts/train_env_model.py --input data/raw/environment.csv --output src/models/environment.pkl
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure `src` is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app.training.env_model import main  # noqa: E402


if __name__ == "__main__":
    main()
