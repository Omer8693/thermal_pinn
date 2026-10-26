"""
experiments/tm_adaptive_k_rectangle_fenics/make_single_leap_heatmap.py
=========================================================================
Heatmap version of the single-leap 10-seed sweep: rows = architecture,
columns = seed, cell = leap-window MAE (°C). Complements make_single_leap_
table.py's per-seed strip plot by making the seed x architecture pattern
scannable at a glance (which seeds are hard, is it consistent across
architectures).

Bayesian uses the patience=10 confirmatory re-run (see memory: identical
to patience=3, proving a true capacity ceiling, not premature stopping).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = EXPERIMENT_ROOT / "reports" / "rectangle"
FIGURES_DIR = EXPERIMENT_ROOT / "figures" / "rectangle"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
ACCEPT_THRESH_C = 10.0
SEEDS = list(range(42, 52))
ARCHS = ["bayesian", "nsga2", "nsga3"]
ARCH_LABELS = {"bayesian": "Bayesian/TPE\n(patience=10)", "nsga2": "NSGA-II", "nsga3": "NSGA-III"}


def load(arch):
    tag = "_patience10" if arch == "bayesian" else ""
    return [json.load(open(REPORTS_DIR / f"single_leap_{arch}_seed{seed}{tag}.json"))["windows"][1]["mae_C"]
            for seed in SEEDS]


def main():
    matrix = np.array([load(a) for a in ARCHS])
    vmax = np.ceil(matrix.max())

    fig, ax = plt.subplots(figsize=(11.5, 4.2), facecolor="white")
    im = ax.imshow(matrix, cmap="YlOrRd", vmin=0, vmax=vmax, aspect="auto")

    for i in range(len(ARCHS)):
        for j in range(len(SEEDS)):
            val = matrix[i, j]
            unsafe = val > ACCEPT_THRESH_C
            txt_color = "white" if val / vmax > 0.55 else "black"
            ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=10,
                    color=txt_color, fontweight="bold" if unsafe else "normal")
            if unsafe:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                            edgecolor="black", linewidth=2.5))

    ax.set_xticks(range(len(SEEDS)))
    ax.set_xticklabels([f"seed\n{s}" for s in SEEDS], fontsize=8.5)
    ax.set_yticks(range(len(ARCHS)))
    ax.set_yticklabels([ARCH_LABELS[a] for a in ARCHS], fontsize=10.5)
    ax.set_xlabel("Model seed", fontsize=10)
    ax.set_title(
        "Single-leap window MAE (°C) — per seed, per architecture\n"
        "Black outline = UNSAFE (>10°C). Rectangle 2D, live FEniCS, window 2 (t=1.5s→30s, k~=19, one shot).",
        fontsize=12, fontweight="bold", pad=10,
    )

    cbar = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.035)
    cbar.set_label("MAE (°C)", fontsize=9.5)
    cbar.ax.axhline(ACCEPT_THRESH_C, color="black", linewidth=1.5, linestyle="--")

    fig.tight_layout()
    out_path = FIGURES_DIR / "single_leap_heatmap.png"
    fig.savefig(out_path, dpi=170, bbox_inches="tight", facecolor="white")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
