"""
experiments/tm_adaptive_k_rectangle_fenics/extract_features.py
==================================================================
Flattens the fixed-k sweep window JSONs (raw_runs/*_live_features.json)
into one flat table, one row per (k, window), for binarize.py / train_tm.py.

Unlike the non-FEniCS experiment, the ML target here is plain SAFE/UNSAFE
(mae_C <= 10 C) per (k, window) sample - not k_next - because the TM's job
is to act as a promotion-safety verifier: at deployment, the controller
proposes a candidate k for the next window, extracts these same FEM-free
features from a probe of that candidate window, and asks TM "is this
window's outcome safe?". Training data does not need cross-k time
alignment for this framing - each (k, window) row is already exactly that
question, answered from the fixed-k sweep's known outcome.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent  # code/ -> experiment root
RAW_DIR = EXPERIMENT_ROOT / "raw_runs"
REPORTS_DIR = EXPERIMENT_ROOT / "reports"

CONTINUOUS_FEATURES = [
    "pde_residual_mean", "pde_residual_max",
    "grad_mean", "grad_max",
    "delta_T_C", "Fo", "Bi",
    "loss_pde", "loss_bc", "loss_end",
]
CATEGORICAL_FEATURES = {
    "phase": ["early", "mid", "late"],
    "arch": ["bayesian", "nsga2", "nsga3"],
}
K_MAX = 5


def load_raw_runs(raw_dir: Path = RAW_DIR) -> list[dict]:
    runs = []
    for path in sorted(raw_dir.glob("*_live_features.json")):
        with open(path, "r", encoding="utf-8") as f:
            runs.append(json.load(f))
    if not runs:
        raise FileNotFoundError(
            f"No *_live_features.json files found in {raw_dir}. "
            f"Run feature_logging_run.py first."
        )
    return runs


def to_dataframe(runs: list[dict]) -> pd.DataFrame:
    rows = []
    for run in runs:
        for w in run["windows"]:
            rows.append({
                "arch": run["arch"],
                "k": w["k"],
                "window": w["window"],
                "t_start": w["t_start"],
                "t_end": w["t_end"],
                "phase": w["phase"],
                "Fo": w["Fo"],
                "Bi": w["Bi"],
                "pde_residual_mean": w["pde_residual_mean"],
                "pde_residual_max": w["pde_residual_max"],
                "grad_mean": w["grad_mean"],
                "grad_max": w["grad_max"],
                "delta_T_C": w["delta_T_C"],
                "loss_pde": w["loss_pde"],
                "loss_bc": w["loss_bc"],
                "loss_end": w["loss_end"],
                "mae_C": w["mae_C"],
                "label": w["label"],
            })
    return pd.DataFrame(rows)


def main() -> None:
    runs = load_raw_runs()
    df = to_dataframe(runs)
    out_path = REPORTS_DIR / "window_features.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"{len(df)} windows from {len(runs)} run(s) -> {out_path}")
    print(df["label"].value_counts())
    print(df.groupby("k")["label"].value_counts())


if __name__ == "__main__":
    main()
