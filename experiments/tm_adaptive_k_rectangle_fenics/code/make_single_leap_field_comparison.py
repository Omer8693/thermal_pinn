"""
experiments/tm_adaptive_k_rectangle_fenics/make_single_leap_field_comparison.py
===================================================================================
Spatial field comparison for the single-leap experiment: FEM reference vs
real PINN predictions for all 3 architectures, at the anchor window end
(t=1.5s, normal k=1 FEM-anchored training) and the leap window end
(t=30s, one-shot k~=19 jump) - same tripcolor+Gouraud style as
make_field_comparison.py's compare_controllers figures.

Reads npz/single_leap_field_snapshots.npz (produced by
single_leap_field_snapshots.py). Bayesian's numbers there are the
patience=10 confirmatory run (see memory: identical to patience=3, a true
capacity ceiling) - this figure shows WHERE spatially that ~9-12C error
concentrates, vs NSGA-II/III's much cleaner leap-window fields.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = EXPERIMENT_ROOT / "npz" / "rectangle"
FIGURES_DIR = EXPERIMENT_ROOT / "figures" / "rectangle"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

ARCHS = ["bayesian", "nsga2", "nsga3"]
ARCH_LABELS = {"bayesian": "Bayesian/TPE", "nsga2": "NSGA-II", "nsga3": "NSGA-III"}
ROW_LABELS = ["anchor\n(t=1.5s, k=1)", "single_leap\n(t=30.0s, k~=19)"]


def draw_field(ax, coords, field, cmap, vmin, vmax, triang, gamma=None):
    if gamma is not None:
        norm = matplotlib.colors.PowerNorm(gamma=gamma, vmin=vmin, vmax=vmax)
        return ax.tripcolor(triang, field, cmap=cmap, norm=norm, shading="gouraud")
    return ax.tripcolor(triang, field, cmap=cmap, vmin=vmin, vmax=vmax, shading="gouraud")


def main():
    d = np.load(RESULTS_DIR / "single_leap_field_snapshots.npz")
    coords = d["coords"]
    triang = mtri.Triangulation(coords[:, 0], coords[:, 1])

    err_vmax = 0.0
    for arch in ARCHS:
        for i in (0, 1):
            err = np.abs(d[f"{arch}_T_ref"][i] - d[f"{arch}_T_pred"][i])
            err_vmax = max(err_vmax, float(np.percentile(err, 99)))
    err_vmax = max(err_vmax, 1.0)

    n_cols = 1 + 2 * len(ARCHS)
    fig, axes = plt.subplots(2, n_cols, figsize=(4.2 * n_cols, 4.4 * 2), constrained_layout=True)
    fig.suptitle(
        "Single-leap experiment — FEM reference vs real PINN predictions, all 3 architectures\n"
        "Rectangle 2D, live FEniCS, seed=42, anchor (t=1.5s) and single-leap (t=30.0s, k~=19, one shot)",
        fontsize=14, fontweight="bold",
    )

    col_titles = ["FEM\nreference"]
    for arch in ARCHS:
        col_titles += [f"{ARCH_LABELS[arch]}\nprediction", f"{ARCH_LABELS[arch]}\n|error|"]

    for row in range(2):
        ref = d["bayesian_T_ref"][row]  # same FEM field for all archs at matching t
        panels = [ref]
        for arch in ARCHS:
            pred = d[f"{arch}_T_pred"][row]
            err = np.abs(d[f"{arch}_T_ref"][row] - pred)
            panels += [pred, err]

        for col, (field, title) in enumerate(zip(panels, col_titles)):
            ax = axes[row, col]
            if col == 0 or col % 2 == 1:
                sc = draw_field(ax, coords, field, "jet", 20, 540, triang)
                label = "Temperature [°C]"
            else:
                sc = draw_field(ax, coords, field, "YlOrRd", 0, err_vmax, triang, gamma=0.4)
                label = "|T_ref − T_pred| [°C]"
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
            if row == 0:
                ax.set_title(title, fontsize=11)
            if col == 0:
                ax.set_ylabel(ROW_LABELS[row], fontsize=10)
            fig.colorbar(sc, ax=ax, pad=0.03, fraction=0.046, label=label if row == 0 else None)

    out_path = FIGURES_DIR / "single_leap_field_comparison.png"
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
