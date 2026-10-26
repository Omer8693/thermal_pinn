"""
experiments/tm_adaptive_k_rectangle_fenics/make_single_leap_tm_heatmap.py
=============================================================================
Heatmap for the TM-gated single-leap experiment (single_leap_tm_experiment.py):
rows = architecture, columns = seed, cell = final leap-window MAE (°C).
Black outline = truly UNSAFE (mae_C > 10°C). A red X marks FALSE-SAFE cells
- the dangerous failure mode where the TM classifier (trained only on
k<=5 data, generalizing out-of-distribution to k~=19) told the retry loop
to stop ("SAFE") while the window was actually still UNSAFE.
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
ARCHS = ["bayesian", "nsga2", "nsga3"]
ARCH_LABELS = {"bayesian": "Bayesian/TPE", "nsga2": "NSGA-II", "nsga3": "NSGA-III"}


def main():
    all_runs = json.load(open(REPORTS_DIR / "single_leap_tm_sweep.json"))
    by_arch = {a: [] for a in ARCHS}
    for run in all_runs:
        by_arch[run["arch"]].append(run)
    seeds = sorted({run["model_seed"] for run in all_runs})

    mae = np.zeros((len(ARCHS), len(seeds)))
    false_safe = np.zeros((len(ARCHS), len(seeds)), dtype=bool)
    unsafe = np.zeros((len(ARCHS), len(seeds)), dtype=bool)
    tm_right = np.zeros((len(ARCHS), len(seeds)), dtype=bool)

    for i, arch in enumerate(ARCHS):
        runs_by_seed = {r["model_seed"]: r for r in by_arch[arch]}
        for j, seed in enumerate(seeds):
            leap = runs_by_seed[seed]["windows"][1]
            mae[i, j] = leap["mae_C"]
            unsafe[i, j] = leap["true_label"] == "UNSAFE"
            false_safe[i, j] = leap["tm_pred_final"] == "SAFE" and leap["true_label"] == "UNSAFE"
            tm_right[i, j] = leap["tm_was_right"]

    vmax = np.ceil(mae.max())
    fig, ax = plt.subplots(figsize=(11.5, 4.4), facecolor="white")
    im = ax.imshow(mae, cmap="YlOrRd", vmin=0, vmax=vmax, aspect="auto")

    for i in range(len(ARCHS)):
        for j in range(len(seeds)):
            val = mae[i, j]
            txt_color = "white" if val / vmax > 0.55 else "black"
            ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=10,
                    color=txt_color, fontweight="bold" if unsafe[i, j] else "normal")
            if unsafe[i, j]:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                            edgecolor="black", linewidth=2.5))
            if false_safe[i, j]:
                ax.plot([j - 0.32, j + 0.32], [i - 0.32, i + 0.32], color="#c00000", linewidth=2.2, zorder=5)
                ax.plot([j - 0.32, j + 0.32], [i + 0.32, i - 0.32], color="#c00000", linewidth=2.2, zorder=5)

    ax.set_xticks(range(len(seeds)))
    ax.set_xticklabels([f"seed\n{s}" for s in seeds], fontsize=8.5)
    ax.set_yticks(range(len(ARCHS)))
    n_right = [int(tm_right[i].sum()) for i in range(len(ARCHS))]
    ax.set_yticklabels([f"{ARCH_LABELS[a]}\n(TM correct {n_right[i]}/10)" for i, a in enumerate(ARCHS)],
                        fontsize=10)
    ax.set_xlabel("Model seed", fontsize=10)
    ax.set_title(
        "TM-gated single-leap: final MAE (°C) — TM decides SAFE/UNSAFE from diagnostics only (no mae_C access)\n"
        "Black outline = truly UNSAFE. Red X = FALSE-SAFE (TM said SAFE while truly UNSAFE — the dangerous error).\n"
        "TM trained only on k<=5 data; the leap window is k~=19 — an out-of-distribution generalization test.",
        fontsize=11.5, fontweight="bold", pad=10,
    )

    cbar = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.035)
    cbar.set_label("Final leap MAE (°C)", fontsize=9.5)
    cbar.ax.axhline(ACCEPT_THRESH_C, color="black", linewidth=1.5, linestyle="--")

    fig.tight_layout()
    out_path = FIGURES_DIR / "single_leap_tm_heatmap.png"
    fig.savefig(out_path, dpi=170, bbox_inches="tight", facecolor="white")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
