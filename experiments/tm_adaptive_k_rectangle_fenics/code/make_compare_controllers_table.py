"""
experiments/tm_adaptive_k_rectangle_fenics/make_compare_controllers_table.py
=============================================================================
Comprehensive PNG report for compare_controllers.py results (Algorithm 3 /
PINN vs TM-guided / PINN+TM vs TM-hybrid / PINN+TM-hybrid), all 3 NAS
architectures, Rectangle 2D, live FEniCS, seed=42 (post seed-bug-fix clean
re-run, 2026-09-14).

Reads reports/compare_controllers{,_nsga2,_nsga3}.json and renders:
  (A) a comprehensive results table — windows/steps, FEM savings, mean/max
      MAE, unsafe windows, total runtime, avg runtime per window, retries.
  (B) grouped bar charts — FEM windows (steps) and total runtime, side by
      side, one group per architecture, one bar per controller.

Run after compare_controllers.py has been run for bayesian, nsga2, nsga3.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent
ACCEPT_THRESH_C = 10.0
GEOMETRY_LABELS = {"rectangle": "Rectangle 2D", "circle": "Circle 2D", "lshape": "L-shape 2D"}

ARCHS = ["bayesian", "nsga2", "nsga3"]
ARCH_LABELS = {"bayesian": "Bayesian/TPE", "nsga2": "NSGA-II", "nsga3": "NSGA-III"}
ARCH_FILES = {
    "bayesian": "compare_controllers.json",
    "nsga2": "compare_controllers_nsga2.json",
    "nsga3": "compare_controllers_nsga3.json",
}
CONTROLLERS = ["algorithm3", "tm_guided", "tm_hybrid"]
CONTROLLER_LABELS = {"algorithm3": "PINN", "tm_guided": "PINN+TM", "tm_hybrid": "PINN+TM-hybrid"}
# Fixed categorical order (dataviz skill: slots 1-3, validated all-pairs CVD-safe)
CONTROLLER_COLORS = {"algorithm3": "#2a78d6", "tm_guided": "#eb6834", "tm_hybrid": "#1baf7a"}


def load_all(reports_dir: Path):
    out = {}
    for arch in ARCHS:
        out[arch] = json.load(open(reports_dir / ARCH_FILES[arch]))
    return out


def safety_color(val, thresh=ACCEPT_THRESH_C):
    return "#dbe9f7" if val <= thresh else "#f6c9c0"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--geometry", default="rectangle", choices=["rectangle", "circle", "lshape"])
    args = p.parse_args()
    geometry = args.geometry
    geometry_label = GEOMETRY_LABELS[geometry]

    reports_dir = EXPERIMENT_ROOT / "reports" / geometry
    figures_dir = EXPERIMENT_ROOT / "figures" / geometry
    figures_dir.mkdir(parents=True, exist_ok=True)

    data = load_all(reports_dir)

    fig = plt.figure(figsize=(15.5, 13.5), facecolor="white")
    gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 0.62], hspace=0.16, top=0.93, bottom=0.05,
                           left=0.02, right=0.98)

    # -----------------------------------------------------------------
    # Panel A: comprehensive table
    # -----------------------------------------------------------------
    axA = fig.add_subplot(gs[0])
    axA.axis("off")
    axA.set_title(
        f"Adaptive-k controller comparison — {geometry_label}, live FEniCS, seed=42\n"
        "Algorithm 3 (PINN)  vs  TM-guided (PINN+TM)  vs  TM-hybrid (PINN+TM-hybrid)",
        fontsize=13.5, fontweight="bold", pad=10,
    )

    col_labels = ["Architecture", "Controller", "Windows\n(FEM calls)", "FEM\nsavings",
                  "Mean MAE\n(°C)", "Max MAE\n(°C)", "Unsafe\nwindows", "Retries /\nboosts",
                  "Total\nruntime (s)", "Avg s /\nwindow"]
    rows, row_max_mae, ctrl_keys = [], [], []
    for arch in ARCHS:
        d = data[arch]
        for ctrl in CONTROLLERS:
            c = d[ctrl]
            unsafe = sum(1 for w in c["windows"] if w["true_label"] == "UNSAFE")
            retries = sum(w.get("retry_count", 0) for w in c["windows"])
            boosts = sum(1 for w in c["windows"] if w.get("n_epochs_used", 800) > 800)
            rb = f"{retries}r / {boosts}b" if (retries or boosts) else "—"
            rows.append([
                ARCH_LABELS[arch], CONTROLLER_LABELS[ctrl], str(c["n_windows"]),
                f"{c['fem_savings_pct']:.1f}%", f"{c['mean_mae']:.2f}", f"{c['max_mae']:.2f}",
                f"{unsafe}/{c['n_windows']}", rb, f"{c['total_s']:.0f}",
                f"{c['total_s'] / c['n_windows']:.1f}",
            ])
            row_max_mae.append(c["max_mae"])
            ctrl_keys.append(ctrl)

    table = axA.table(cellText=rows, colLabels=col_labels, cellLoc="center",
                       bbox=[0.0, 0.06, 1.0, 0.84],
                       colWidths=[0.13, 0.15, 0.10, 0.09, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10])
    table.auto_set_font_size(False)
    table.set_fontsize(10.5)
    for j in range(len(col_labels)):
        table[0, j].set_facecolor("#2c3e50")
        table[0, j].set_text_props(color="white", fontweight="bold")
    for i in range(len(rows)):
        r = i + 1
        table[r, 0].set_text_props(fontweight="bold")
        table[r, 1].set_text_props(color=CONTROLLER_COLORS[ctrl_keys[i]], fontweight="bold")
        table[r, 5].set_facecolor(safety_color(row_max_mae[i]))
        if ctrl_keys[i] == "tm_hybrid":
            table[r, 3].set_facecolor("#d5f2d5")
        # thin separator between architecture blocks
        if i % 3 == 0 and i > 0:
            for j in range(len(col_labels)):
                table[r, j].set_edgecolor("#888888")
                table[r, j].set_linewidth(1.4)

    axA.text(
        0.0, 0.0,
        f"Max MAE colored against the {ACCEPT_THRESH_C:.0f}°C acceptance threshold (light blue = safe, light red = unsafe). "
        "'Retries/boosts' counts reactive retry-until-safe episodes and proactive epoch-boosted windows (TM-hybrid only). "
        "All rows share the same live FEniCS reference, model seed=42, and starting weights within an architecture.",
        transform=axA.transAxes, fontsize=8.5, color="#555555", wrap=True,
    )

    # -----------------------------------------------------------------
    # Panel B: grouped bar charts — windows (steps) and runtime
    # -----------------------------------------------------------------
    gsB = gs[1].subgridspec(1, 2, wspace=0.18)
    axW = fig.add_subplot(gsB[0])
    axT = fig.add_subplot(gsB[1])

    x = np.arange(len(ARCHS))
    width = 0.26
    for i, ctrl in enumerate(CONTROLLERS):
        offset = (i - 1) * width
        windows = [data[a][ctrl]["n_windows"] for a in ARCHS]
        runtimes = [data[a][ctrl]["total_s"] for a in ARCHS]
        color = CONTROLLER_COLORS[ctrl]
        bw = axW.bar(x + offset, windows, width, label=CONTROLLER_LABELS[ctrl], color=color)
        bt = axT.bar(x + offset, runtimes, width, label=CONTROLLER_LABELS[ctrl], color=color)
        axW.bar_label(bw, fontsize=8, padding=2)
        axT.bar_label(bt, fmt="%.0f", fontsize=8, padding=2)

    axW.axhline(20, color="#999999", linestyle="--", linewidth=1, zorder=0)
    axW.text(-0.42, 20.4, "k=1 baseline (20)", fontsize=7.5, color="#777777", ha="left")
    axW.set_xticks(x)
    axW.set_xticklabels([ARCH_LABELS[a] for a in ARCHS])
    axW.set_ylabel("FEM windows (steps)")
    axW.set_title("Steps to complete the 30 s cooling curve", fontsize=11, fontweight="bold")
    axW.spines[["top", "right"]].set_visible(False)
    axW.legend(fontsize=8.5, frameon=False, loc="upper right")

    axT.set_xticks(x)
    axT.set_xticklabels([ARCH_LABELS[a] for a in ARCHS])
    axT.set_ylabel("Total wall-clock runtime (s)")
    axT.set_title("Runtime to complete the 30 s cooling curve", fontsize=11, fontweight="bold")
    axT.spines[["top", "right"]].set_visible(False)
    axT.legend(fontsize=8.5, frameon=False, loc="upper right")

    fig.suptitle(
        f"NAS-PINN + Adaptive-k + Tsetlin Machine — {geometry_label}, Live FEniCS FEM Reference",
        fontsize=15, fontweight="bold", y=0.985,
    )

    out_path = figures_dir / "compare_controllers_table.png"
    fig.savefig(out_path, dpi=170, bbox_inches="tight", facecolor="white")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
