"""Repo-wide path constants."""
from pathlib import Path

_ROOT          = Path(__file__).resolve().parent
CHECKPOINT_DIR = _ROOT / "checkpoints"
DATA_DIR       = _ROOT / "data"
ASSETS_DIR     = _ROOT / "assets"
