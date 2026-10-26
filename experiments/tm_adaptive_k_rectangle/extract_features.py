"""
experiments/tm_adaptive_k_rectangle/extract_features.py
==========================================================
Flattens the per-seed window-level JSON files produced by
feature_logging_run.py (raw_runs/*.json) into one flat table (list of
dicts / pandas DataFrame), one row per window, ready for binarize.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent / "raw_runs"

CONTINUOUS_FEATURES = [
    "pde_residual_mean", "pde_residual_max",
    "grad_mean", "grad_max",
    "delta_T_C", "Fo", "Bi",
]
CATEGORICAL_FEATURES = {
    "phase": ["early", "mid", "late"],
    "arch": ["bayesian", "nsga2", "nsga3"],
}
ORDINAL_FEATURES = ["k_prev"]  # 0 (=no previous window) .. 5


def load_raw_runs(raw_dir: Path = RAW_DIR) -> list[dict]:
    runs = []
    for path in sorted(raw_dir.glob("*_features.json")):
        with open(path, "r", encoding="utf-8") as f:
            runs.append(json.load(f))
    if not runs:
        raise FileNotFoundError(
            f"No *_features.json files found in {raw_dir}. "
            f"Run feature_logging_run.py first."
        )
    return runs


def to_dataframe(runs: list[dict]) -> pd.DataFrame:
    """One row per window, PLUS k_next = k_used of the *following* window in
    the same run (the quantity the TM controller actually needs to predict,
    since Algorithm 3 decides window i+1's k from window i's measurements).
    The last window of each run has no next-window k and is dropped.
    """
    rows = []
    for run in runs:
        windows = run["windows"]
        for i, w in enumerate(windows[:-1]):
            k_next = windows[i + 1]["k_used"]
            row = {
                "arch": run["arch"],
                "seed": run["seed"],
                "domain": run["domain"],
                "window": w["window"],
                "t_start": w["t_start"],
                "t_end": w["t_end"],
                "k_used": w["k_used"],
                "k_prev": w["k_prev"] if w["k_prev"] is not None else 0,
                "k_next": k_next,
                "phase": w["phase"],
                "Fo": w["Fo"],
                "Bi": w["Bi"],
                "pde_residual_mean": w["pde_residual_mean"],
                "pde_residual_max": w["pde_residual_max"],
                "grad_mean": w["grad_mean"],
                "grad_max": w["grad_max"],
                "delta_T_C": w["delta_T_C"],
                "mae_C": w["mae_C"],
                "label": w["label"],
            }
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    runs = load_raw_runs()
    df = to_dataframe(runs)
    out_path = Path(__file__).resolve().parent / "results" / "window_features.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"{len(df)} windows from {len(runs)} run(s) -> {out_path}")
    print("label (SAFE/UNSAFE, informational only):")
    print(df["label"].value_counts())
    print("k_next (primary ML target) distribution:")
    print(df["k_next"].value_counts().sort_index())
    print(df.groupby("arch")["seed"].nunique())


if __name__ == "__main__":
    main()
