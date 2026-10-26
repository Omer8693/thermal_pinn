"""
experiments/tm_adaptive_k_rectangle_fenics/make_compare_controllers_heatmap.py
=================================================================================
Heatmap version of the 10-seed compare_controllers sweep: 3 side-by-side
panels (Algorithm 3 / TM-guided / TM-hybrid), each rows = architecture,
columns = seed, cell = max window MAE (°C) for that run - max rather than
mean because max MAE is what actually determines the UNSAFE/SAFE verdict
for the run. Same color scale across all 3 panels so they're directly
comparable. Complements make_compare_controllers_10seed_table.py's
mean+/-std table by showing exactly which seeds fail for which controller.
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
ARCH_LABELS = {"bayesian": "Bayesian/TPE", "nsga2": "NSGA-II", "nsga3": "NSGA-III"}
CONTROLLERS = ["algorithm3", "tm_guided", "tm_hybrid"]
CONTROLLER_LABELS = {"algorithm3": "PINN", "tm_guided": "PINN+TM", "tm_hybrid": "PINN+TM-hybrid"}


def fname(arch: str, seed: int) -> Path:
    tag = "" if arch == "bayesian" else f"_{arch}"
    if seed != 42:
        tag += f"_seed{seed}"
    return REPORTS_DIR / f"compare_controllers{tag}.json"


def load_matrix(ctrl):
    rows = []
    for arch in ARCHS:
        row = []
        for seed in SEEDS:
            d = json.load(open(fname(arch, seed)))
            row.append(d[ctrl]["max_mae"])
        rows.append(row)
    return np.array(rows)


def main():
    matrices = {ctrl: load_matrix(ctrl) for ctrl in CONTROLLERS}
    vmax = np.ceil(max(m.max() for m in matrices.values()))

    fig, axes = plt.subplots(1, 3, figsize=(21, 4.6), facecolor="white", sharey=True)

    for ax, ctrl in zip(axes, CONTROLLERS):
        matrix = matrices[ctrl]
        im = ax.imshow(matrix, cmap="YlOrRd", vmin=0, vmax=vmax, aspect="auto")
        for i in range(len(ARCHS)):
            for j in range(len(SEEDS)):
                val = matrix[i, j]
                unsafe = val > ACCEPT_THRESH_C
                txt_color = "white" if val / vmax > 0.55 else "black"
                ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=9.5,
                        color=txt_color, fontweight="bold" if unsafe else "normal")
                if unsafe:
                    ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                                edgecolor="black", linewidth=2.3))
        ax.set_xticks(range(len(SEEDS)))
        ax.set_xticklabels([str(s) for s in SEEDS], fontsize=8.5)
        ax.set_xlabel("Model seed", fontsize=9.5)
        ax.set_title(CONTROLLER_LABELS[ctrl], fontsize=13, fontweight="bold", pad=8)

    axes[0].set_yticks(range(len(ARCHS)))
    axes[0].set_yticklabels([ARCH_LABELS[a] for a in ARCHS], fontsize=11)

    fig.suptitle(
        "Adaptive-k controller comparison — max window MAE (°C) per seed, per architecture\n"
        "Black outline = UNSAFE (>10°C). Rectangle 2D, live FEniCS, 10-seed sweep (seeds 42-51).",
        fontsize=13.5, fontweight="bold", y=1.06,
    )

    cbar = fig.colorbar(im, ax=axes, pad=0.015, fraction=0.02)
    cbar.set_label("Max window MAE (°C)", fontsize=9.5)
    cbar.ax.axhline(ACCEPT_THRESH_C, color="black", linewidth=1.5, linestyle="--")

    out_path = FIGURES_DIR / "compare_controllers_heatmap.png"
    fig.savefig(out_path, dpi=170, bbox_inches="tight", facecolor="white")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
