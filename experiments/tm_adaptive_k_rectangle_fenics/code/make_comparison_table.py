"""
experiments/tm_adaptive_k_rectangle_fenics/make_comparison_table.py
=======================================================================
Renders one PNG with two tables:
  (A) Fixed-k sweep MAE: thesis-reported (results_2d.tex, 10-seed mean)
      vs this experiment's live-FEniCS single-seed re-run.
  (B) Adaptive-k controller comparison: Algorithm 3 (threshold) vs
      TM-guided, for all three architectures.

Run after feature_logging_run.py + compare_controllers.py have been run
for bayesian, nsga2, and nsga3.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent  # code/ -> experiment root
RESULTS_DIR = EXPERIMENT_ROOT / "npz"
FIGURES_DIR = EXPERIMENT_ROOT / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR = EXPERIMENT_ROOT / "raw_runs"
ACCEPT_THRESH_C = 10.0

ARCHS = ["bayesian", "nsga2", "nsga3"]
ARCH_LABELS = {"bayesian": "Bayesian/TPE", "nsga2": "NSGA-II", "nsga3": "NSGA-III"}

# Thesis-reported 10-seed mean MAE, Rectangle 2D, results_2d.tex
THESIS_FIXED_K = {
    "bayesian": [2.12, 2.81, 3.19, 3.69, 4.03],
    "nsga2":    [3.44, 5.40, 6.76, 8.33, 9.66],
    "nsga3":    [3.52, 5.11, 6.10, 7.95, 9.28],
}

# Original repo Algorithm 3 adaptive-k results (checkpoints/*_adaptive*_metrics.json),
# produced with the pre-computed/interpolated npz FEMReference (h=700), NOT live FEniCS.
# bayesian = mean over 10 independent seeds; nsga2/nsga3 = single run each (no seed sweep
# was ever run for them in the original repo).
ORIGINAL_ALGO3 = {
    "bayesian": {"mean_mae": 6.24, "max_mae": None, "n_windows": 17.6, "fem_savings_pct": 12.0,
                 "n_unsafe": 1, "n_total": 176, "note": "10-seed mean"},
    "nsga2":    {"mean_mae": 4.64, "max_mae": 20.64, "n_windows": 11, "fem_savings_pct": 45.0,
                 "n_unsafe": 1, "n_total": 11, "note": "single run"},
    "nsga3":    {"mean_mae": 4.79, "max_mae": 18.92, "n_windows": 11, "fem_savings_pct": 45.0,
                 "n_unsafe": 1, "n_total": 11, "note": "single run"},
}


def load_our_fixed_k():
    out = {}
    for arch in ARCHS:
        vals = []
        for k in range(1, 6):
            d = json.load(open(RAW_DIR / f"rectangle_{arch}_k{k}_dim2_live_features.json"))
            vals.append(d["mean_mae"])
        out[arch] = vals
    return out


N_FEM_K1 = 20  # ceil(T_TOTAL / DT_FEM) = ceil(30 / 1.5), same constant as compare_controllers.py


def load_compare():
    """Reads results/field_snapshots_{arch}.npz instead of the older
    compare_controllers_{arch}.json - the npz is what field_snapshots.py /
    the boost-epoch safety fix actually updates (see
    tm_adaptive_k_rectangle_experiment.md memory: boost_epochs=6400,
    boost_windows=3 eliminated all NSGA-II/III unsafe windows), whereas the
    compare_controllers_*.json files are the older, now-stale
    baseline (800-epoch, unboosted) runs and were never regenerated with
    the fix."""
    out = {}
    for arch in ARCHS:
        suffix = "" if arch == "bayesian" else f"_{arch}"
        npz = np.load(RESULTS_DIR / f"field_snapshots{suffix}.npz")
        arch_out = {}
        for ctrl_key in ("algorithm3", "tm_guided"):
            mae = npz[f"{ctrl_key}_mae"]
            n_windows = len(mae)
            arch_out[ctrl_key] = {
                "n_windows": n_windows,
                "fem_savings_pct": (1.0 - n_windows / N_FEM_K1) * 100.0,
                "mean_mae": float(mae.mean()),
                "max_mae": float(mae.max()),
                "total_s": float(npz[f"{ctrl_key}_runtime_s"].sum()),
                "windows": [{"true_label": "UNSAFE" if m > ACCEPT_THRESH_C else "SAFE"} for m in mae],
            }
        out[arch] = arch_out
    return out


def cell_color(val, thresh=ACCEPT_THRESH_C):
    if val <= thresh:
        return "#dbe9f7"  # light blue - within tolerance (matches thesis convention)
    return "#f6c9c0"      # light red - above tolerance


def main():
    our_fixed_k = load_our_fixed_k()
    compare = load_compare()

    fig = plt.figure(figsize=(14, 12.5), facecolor="white")
    gs = fig.add_gridspec(2, 1, height_ratios=[0.72, 1.0], hspace=0.05, top=0.93, bottom=0.03,
                            left=0.02, right=0.99)

    # ---------------------------------------------------------------
    # Table A: fixed-k sweep, thesis vs ours
    # ---------------------------------------------------------------
    axA = fig.add_subplot(gs[0])
    axA.axis("off")
    axA.set_title(
        "A) Fixed-k sweep — Rectangle 2D — MAE (°C)\n"
        "Thesis report (results_2d.tex, 10-seed mean)  vs  This experiment (live FEniCS, single seed=42)",
        fontsize=13, fontweight="bold", pad=8,
    )

    col_labels = ["Architecture", "Source", "k=1\n(0%)", "k=2\n(50%)", "k=3\n(65%)", "k=4\n(75%)", "k=5\n(80%)"]
    rows = []
    row_colors = []
    for arch in ARCHS:
        for src, vals in [("Thesis report", THESIS_FIXED_K[arch]), ("Ours (FEniCS)", our_fixed_k[arch])]:
            rows.append([ARCH_LABELS[arch], src] + [f"{v:.2f}" for v in vals])
            row_colors.append([cell_color(v) for v in vals])

    tableA = axA.table(cellText=rows, colLabels=col_labels, cellLoc="center",
                        bbox=[0.0, 0.12, 1.0, 0.8],
                        colWidths=[0.16, 0.16, 0.136, 0.136, 0.136, 0.136, 0.136])
    tableA.auto_set_font_size(False)
    tableA.set_fontsize(10.5)
    for j in range(len(col_labels)):
        tableA[0, j].set_facecolor("#2c3e50")
        tableA[0, j].set_text_props(color="white", fontweight="bold")
    for i, arch in enumerate(ARCHS):
        for r in (0, 1):
            row_idx = i * 2 + r + 1
            tableA[row_idx, 0].set_text_props(fontweight="bold")
            tableA[row_idx, 1].set_text_props(style="italic")
            for j, col in enumerate(range(2, 7)):
                tableA[row_idx, col].set_facecolor(row_colors[i * 2 + r][j])
        # merge visual grouping: thin separator after each arch pair
    axA.text(
        0.0, 0.04,
        f"Color: light blue = below the engineering acceptance threshold ({ACCEPT_THRESH_C:.0f}°C), light red = above it.  "
        f"Thesis values are a 10-seed mean; ours is a single seed (42) — exact numerical match is not expected, "
        f"compare the pattern (ranking across architectures, growth with k) instead.",
        transform=axA.transAxes, fontsize=8.5, color="#555555", wrap=True,
    )

    # ---------------------------------------------------------------
    # Table B: adaptive-k controller comparison
    # ---------------------------------------------------------------
    axB = fig.add_subplot(gs[1])
    axB.axis("off")
    axB.set_title(
        "B) Adaptive-k controller comparison — Rectangle 2D — PINN vs PINN+TM",
        fontsize=13, fontweight="bold", pad=8,
    )

    col_labels_b = ["Architecture", "Controller", "FEM engine", "Windows\n(FEM calls)", "FEM\nsavings",
                    "Mean MAE\n(°C)", "Max MAE\n(°C)", "Unsafe\nwindows", "Runtime (s)"]
    rows_b = []
    colors_b = []
    tm_row_flags = []
    for arch in ARCHS:
        # Row 1: original repo Algorithm 3 (npz-interpolated FEMReference, h=700)
        o = ORIGINAL_ALGO3[arch]
        n_windows_str = f"{o['n_windows']:.1f} (avg)" if o["n_windows"] % 1 else str(int(o["n_windows"]))
        rows_b.append([
            ARCH_LABELS[arch], f"PINN\n({o['note']})", "npz (h=700)", n_windows_str,
            f"{o['fem_savings_pct']:.1f}%", f"{o['mean_mae']:.2f}",
            f"{o['max_mae']:.2f}" if o["max_mae"] is not None else "n/a",
            f"{o['n_unsafe']}/{o['n_total']}", "n/a",
        ])
        colors_b.append(cell_color(o["max_mae"]) if o["max_mae"] is not None else "white")
        tm_row_flags.append(False)

        # Rows 2-3: this experiment, live FEniCS, single seed=42
        d = compare[arch]
        for ctrl_key, ctrl_label in [("algorithm3", "PINN"), ("tm_guided", "PINN+TM")]:
            c = d[ctrl_key]
            n_unsafe = sum(1 for w in c["windows"] if w["true_label"] == "UNSAFE")
            rows_b.append([
                ARCH_LABELS[arch], ctrl_label, "live FEniCS", str(c["n_windows"]),
                f"{c['fem_savings_pct']:.1f}%", f"{c['mean_mae']:.2f}",
                f"{c['max_mae']:.2f}", f"{n_unsafe}/{c['n_windows']}", f"{c['total_s']:.0f}",
            ])
            colors_b.append(cell_color(c["max_mae"]))
            tm_row_flags.append(ctrl_key == "tm_guided")

    tableB = axB.table(cellText=rows_b, colLabels=col_labels_b, cellLoc="center",
                        bbox=[0.0, 0.10, 1.0, 0.85],
                        colWidths=[0.135, 0.155, 0.11, 0.115, 0.10, 0.115, 0.105, 0.11, 0.105])
    tableB.auto_set_font_size(False)
    tableB.set_fontsize(10)
    for j in range(len(col_labels_b)):
        tableB[0, j].set_facecolor("#2c3e50")
        tableB[0, j].set_text_props(color="white", fontweight="bold")
    for i in range(len(rows_b)):
        row_idx = i + 1
        tableB[row_idx, 0].set_text_props(fontweight="bold")
        is_tm = tm_row_flags[i]
        tableB[row_idx, 1].set_text_props(
            color="#1a6b1a" if is_tm else "#333333", fontweight="bold" if is_tm else "normal",
        )
        tableB[row_idx, 2].set_text_props(style="italic", fontsize=9)
        tableB[row_idx, 6].set_facecolor(colors_b[i])  # max MAE column colored by safety
        tableB[row_idx, 4].set_facecolor("#d5f2d5" if is_tm else "white")  # highlight savings for TM

    axB.text(
        0.0, 0.05,
        "'FEM engine' shows which FEM reference produced each row: 'npz (h=700)' = the repo's original pre-computed/"
        "interpolated reference (checkpoints/*_adaptive*_metrics.json, bayesian = 10-seed mean, NSGA-II/III = single "
        "run, no seed sweep ever run for them originally); 'live FEniCS' = this experiment's real-time dolfin solve "
        "(both PINN and PINN+TM here use the SAME live engine and the same initial weights, seed=42). "
        "Bold green rows = PINN+TM. 'Max MAE' colored against the 10°C threshold.",
        transform=axB.transAxes, fontsize=8, color="#555555", wrap=True,
    )

    fig.suptitle(
        "NAS-PINN + Adaptive-k + Tsetlin Machine — Rectangle 2D, Live FEniCS FEM Reference",
        fontsize=15, fontweight="bold", y=0.995,
    )

    out_path = FIGURES_DIR / "comparison_table.png"
    fig.savefig(out_path, dpi=170, bbox_inches="tight", facecolor="white")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
