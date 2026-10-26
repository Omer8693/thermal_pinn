"""
experiments/tm_adaptive_k_rectangle_fenics/make_warmstart_comparison.py
=====================================================================
Compares the ORIGINAL trainer (fresh Adam + LR reset to 1e-3 every
window, results/field_snapshots.npz) against the persistent-optimizer
variant (results/field_snapshots_warmstart.npz, see persistent_trainer.py)
head-to-head: does carrying Adam's momentum across windows and softening
the LR reset (continuation_lr=1e-4) actually smooth the window-transition
"kick" visible in rectangle_loss_curves.png, and does it help or hurt
accuracy?

Produces results/rectangle_warmstart_comparison.png:
  - top row: MAE(t) trajectory, original vs persistent-optimizer, for
    both PINN and PINN+TM.
  - bottom row: loss vs cumulative epoch (total loss only, log scale),
    original vs persistent-optimizer, so the size of the spike at each
    window boundary can be compared directly.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent  # code/ -> experiment root
RESULTS_DIR = EXPERIMENT_ROOT / "npz"
FIGURES_DIR = EXPERIMENT_ROOT / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
DISPLAY_NAME = {"algorithm3": "PINN", "tm_guided": "PINN+TM"}


def load():
    old = np.load(RESULTS_DIR / "field_snapshots.npz")
    new = np.load(RESULTS_DIR / "field_snapshots_warmstart.npz")
    return {k: old[k] for k in old.files}, {k: new[k] for k in new.files}


def main():
    old, new = load()

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    fig.suptitle(
        "Rectangle, Bayesian — original (fresh Adam + LR reset each window) "
        "vs persistent-optimizer (momentum kept, continuation_lr=1e-4)",
        fontsize=12.5, fontweight="bold",
    )

    for col, ctrl in enumerate(("algorithm3", "tm_guided")):
        ax = axes[0, col]
        ax.plot(old[f"{ctrl}_t"], old[f"{ctrl}_mae"], "o-", color="tab:blue", label="original")
        ax.plot(new[f"{ctrl}_t"], new[f"{ctrl}_mae"], "s--", color="tab:green", label="persistent-optimizer")
        ax.axhline(10.0, color="black", linestyle=":", linewidth=1.2)
        ax.set_title(f"{DISPLAY_NAME[ctrl]} — MAE(t)  "
                     f"(windows: {len(old[f'{ctrl}_t'])}→{len(new[f'{ctrl}_t'])}, "
                     f"mean MAE: {old[f'{ctrl}_mae'].mean():.2f}→{new[f'{ctrl}_mae'].mean():.2f}°C)",
                     fontsize=10)
        ax.set_xlabel("time [s]")
        ax.set_ylabel("window MAE [°C]")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)

        ax2 = axes[1, col]
        for data, color, label in ((old, "tab:blue", "original"), (new, "tab:green", "persistent-optimizer")):
            loss_total = data[f"{ctrl}_loss_total"]
            n_windows, n_epochs = loss_total.shape
            x = np.arange(n_windows * n_epochs)
            ax2.plot(x, loss_total.ravel(), color=color, linewidth=0.8, alpha=0.85, label=label)
            for w in range(1, n_windows):
                ax2.axvline(w * n_epochs, color=color, linewidth=0.4, linestyle=":", alpha=0.5)
        ax2.set_yscale("log")
        ax2.set_title(f"{DISPLAY_NAME[ctrl]} — total loss vs cumulative epoch", fontsize=10)
        ax2.set_xlabel("cumulative epoch (own run)")
        ax2.set_ylabel("loss (log scale)")
        ax2.legend(fontsize=8)
        ax2.grid(alpha=0.25)

    out_path = FIGURES_DIR / "rectangle_warmstart_comparison.png"
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
