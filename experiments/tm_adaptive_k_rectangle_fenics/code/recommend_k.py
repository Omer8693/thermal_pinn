"""
experiments/tm_adaptive_k_rectangle_fenics/recommend_k.py
=====================================================================
Offline, phase/geometry-aware "what k should I use" helper - separate
from the online tm_hybrid controller (hybrid_controller.py), which
still decides k+-1 step by step from a single window's own live
features.

This module instead aggregates the fixed-k sweep data already on disk
(raw_runs/{geometry}_{arch}_k{1..5}_dim2_live_features.json, produced by
feature_logging_run.py) into a per-(phase, k) SAFE-rate table, and
answers "what is the largest k that empirically stayed SAFE this deep
into the cooldown" - a coarse, aggregate prior, reported ALONGSIDE
tm_hybrid's own online decision in compare_report.md, not wired in to
replace it. Memory records that an online, per-window *multiclass
k_next* target was tried and abandoned (labels didn't separate
cleanly) - this is a different mechanism (offline, phase-aggregated
SAFE-rate over many fixed-k windows, not a per-window online
classifier), so it isn't re-treading that dead end, but it is
deliberately NOT claimed as a drop-in controller replacement.

Only Rectangle currently has fixed-k sweep data (k=1..5) for all three
archs. Circle/L-shape need their own feature_logging_run.py sweep first
(the already-planned next step) - load_phase_k_table raises a clear
FileNotFoundError-based message rather than silently falling back to
Rectangle's numbers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_features import RAW_DIR, load_raw_runs, to_dataframe

ACCEPT_THRESH_C = 10.0
K_MIN = 1


def load_phase_k_table(arch: str, geometry: str = "rectangle",
                        raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """One row per (phase, k): mean MAE, SAFE-rate, n windows - pooled
    across all fixed-k sweep files found for this (geometry, arch)."""
    pattern = f"{geometry}_{arch}_k*_dim2_live_features.json"
    matches = sorted(raw_dir.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f"No fixed-k sweep data for geometry={geometry!r} arch={arch!r} "
            f"(looked for {raw_dir / pattern}). Run "
            f"feature_logging_run.py --arch {arch} --k-values 1 2 3 4 5 --cuda "
            f"for this geometry first - recommend_k() will not guess from a "
            f"different geometry's data."
        )
    runs = [r for r in load_raw_runs(raw_dir) if r["domain"] == geometry and r["arch"] == arch]
    df = to_dataframe(runs)
    grouped = df.groupby(["phase", "k"]).agg(
        mean_mae=("mae_C", "mean"),
        safe_rate=("label", lambda s: float((s == "SAFE").mean())),
        n_windows=("mae_C", "size"),
    ).reset_index()
    return grouped


def recommend_k(phase: str, arch: str = "bayesian", geometry: str = "rectangle",
                 safe_rate_min: float = 1.0, raw_dir: Path = RAW_DIR) -> int:
    """Largest k whose SAFE-rate in this phase is >= safe_rate_min, among
    the k values actually swept; falls back to K_MIN if none qualify."""
    table = load_phase_k_table(arch, geometry, raw_dir)
    phase_rows = table[table["phase"] == phase]
    qualifying = phase_rows[phase_rows["safe_rate"] >= safe_rate_min]
    if qualifying.empty:
        return K_MIN
    return int(qualifying["k"].max())


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", default="bayesian", choices=["bayesian", "nsga2", "nsga3"])
    parser.add_argument("--geometry", default="rectangle")
    parser.add_argument("--safe-rate-min", type=float, default=1.0)
    args = parser.parse_args()

    table = load_phase_k_table(args.arch, args.geometry)
    pd.set_option("display.width", 100)
    print(table.sort_values(["phase", "k"]).to_string(index=False))
    print()
    for phase in ("early", "mid", "late"):
        if phase in table["phase"].unique():
            k = recommend_k(phase, args.arch, args.geometry, args.safe_rate_min)
            print(f"recommend_k(phase={phase!r}, arch={args.arch!r}, "
                  f"geometry={args.geometry!r}, safe_rate_min={args.safe_rate_min}) = {k}")


if __name__ == "__main__":
    main()
