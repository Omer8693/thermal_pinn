"""
experiments/tm_adaptive_k_rectangle_fenics/make_single_leap_table.py
=======================================================================
Comprehensive PNG report for the single-leap experiment (window 1: normal
FEM-anchored k=1, t=0->1.5s; window 2: skip straight to t=30s, k~=19),
10-seed sweep, all 3 NAS architectures, Rectangle 2D, live FEniCS.

Bayesian uses the patience=10 CONFIRMATORY re-run (reports/single_leap_
bayesian_seed{42..51}_patience10.json) - patience=3 vs patience=10 gave
IDENTICAL best_epoch/MAE per seed (see memory: "Bayesian patience
investigation"), proving the ~9-12C leap MAE band is a genuine architecture
capacity ceiling for Bayesian on this one-shot 28.5s window, not an
artifact of stopping too early. NSGA-II/III use the original patience=3
sweep (reports/single_leap_{nsga2,nsga3}_seed{42..51}.json) since neither
ever hit the epoch ceiling there either - already fully converged.

Run after both single_leap_experiment.py sweeps exist.
"""

from __future__ import annotations

import json
import statistics
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
ARCH_NET = {
    "bayesian": "5×151 ReLU, 92.7k params",
    "nsga2": "3×153 tanh, 48.0k params",
    "nsga3": "3×75 tanh, 11.9k params",
}
ARCH_COLORS = {"bayesian": "#2a78d6", "nsga2": "#eb6834", "nsga3": "#1baf7a"}
ARCH_SOURCE = {
    "bayesian": "patience=10 confirmatory re-run\n(identical to patience=3 — true asymptote)",
    "nsga2": "patience=3 (original sweep,\nnever hit epoch ceiling)",
    "nsga3": "patience=3 (original sweep,\nnever hit epoch ceiling)",
}


def load(arch):
    tag = "_patience10" if arch == "bayesian" else ""
    rows = []
    for seed in SEEDS:
        d = json.load(open(REPORTS_DIR / f"single_leap_{arch}_seed{seed}{tag}.json"))
        anchor, leap = d["windows"]
        rows.append(dict(seed=seed, anchor_mae=anchor["mae_C"], leap_mae=leap["mae_C"],
                          leap_l2=leap["l2_rel"],
                          leap_safe=leap["true_label"] == "SAFE", leap_epochs=leap["n_epochs_used"],
                          total_s=d["total_s"]))
    return rows


def main():
    data = {a: load(a) for a in ARCHS}

    fig = plt.figure(figsize=(17.5, 12.5), facecolor="white")
    gs = fig.add_gridspec(2, 1, height_ratios=[0.62, 1.0], hspace=0.2, top=0.92, bottom=0.06,
                           left=0.02, right=0.98)

    # -----------------------------------------------------------------
    # Panel A: comprehensive table
    # -----------------------------------------------------------------
    axA = fig.add_subplot(gs[0])
    axA.axis("off")
    axA.set_title(
        "Single-leap experiment — window 2 skips t=1.5s→30s directly (k~=19, one shot)\n"
        "10-seed sweep (seeds 42-51), Rectangle 2D, live FEniCS",
        fontsize=13.5, fontweight="bold", pad=10,
    )

    col_labels = ["Architecture", "Network", "Anchor MAE\n(°C)", "Leap SAFE\nrate",
                  "Leap MAE\n(°C, mean±std)", "Leap L2 rel\nerror (mean±std)",
                  "Leap epochs\n(mean, range)",
                  "Total runtime\n(s, mean±std)", "Data source"]
    rows = []
    safe_rates = []
    for arch in ARCHS:
        v = data[arch]
        anchor_maes = [r["anchor_mae"] for r in v]
        leap_maes = [r["leap_mae"] for r in v]
        leap_l2s = [r["leap_l2"] for r in v]
        eps = [r["leap_epochs"] for r in v]
        rts = [r["total_s"] for r in v]
        n_safe = sum(1 for r in v if r["leap_safe"])
        safe_rates.append(n_safe)
        rows.append([
            ARCH_LABELS[arch], ARCH_NET[arch],
            f"{statistics.mean(anchor_maes):.2f}±{statistics.stdev(anchor_maes):.2f}",
            f"{n_safe}/10",
            f"{statistics.mean(leap_maes):.2f}±{statistics.stdev(leap_maes):.2f}",
            f"{statistics.mean(leap_l2s):.4f}±{statistics.stdev(leap_l2s):.4f}",
            f"{statistics.mean(eps):.0f}  ({min(eps)}-{max(eps)})",
            f"{statistics.mean(rts):.0f}±{statistics.stdev(rts):.0f}",
            ARCH_SOURCE[arch],
        ])

    table = axA.table(cellText=rows, colLabels=col_labels, cellLoc="center",
                       bbox=[0.0, 0.05, 1.0, 0.82],
                       colWidths=[0.11, 0.15, 0.09, 0.08, 0.125, 0.125, 0.13, 0.12, 0.17])
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    for j in range(len(col_labels)):
        table[0, j].set_facecolor("#2c3e50")
        table[0, j].set_text_props(color="white", fontweight="bold")
    for i, arch in enumerate(ARCHS):
        r = i + 1
        table[r, 0].set_text_props(fontweight="bold", color=ARCH_COLORS[arch])
        table[r, 1].set_text_props(style="italic", fontsize=9)
        table[r, 3].set_facecolor("#dbe9f7" if safe_rates[i] == 10 else
                                   ("#f6c9c0" if safe_rates[i] <= 3 else "#fde3b8"))
        table[r, 8].set_text_props(fontsize=8, color="#555555")

    axA.text(
        0.0, 0.0,
        "Leap SAFE colored: light blue = 10/10 seeds safe, light red = <=3/10. Bayesian's numbers come from a "
        "patience=10 CONFIRMATORY re-run (8000-epoch plateau window vs the original 2400) that reproduced the "
        "exact same best-epoch/MAE per seed as patience=3 — proving the ~9-12°C band is a genuine architecture "
        "capacity ceiling for this one-shot 28.5s window, not premature stopping.",
        transform=axA.transAxes, fontsize=8.3, color="#555555", wrap=True,
    )

    # -----------------------------------------------------------------
    # Panel B: per-seed strip plot (left) + epoch cost bar chart (right)
    # -----------------------------------------------------------------
    gsB = gs[1].subgridspec(1, 2, wspace=0.22, width_ratios=[1.1, 1.0])
    axS = fig.add_subplot(gsB[0])
    axE = fig.add_subplot(gsB[1])

    rng = np.random.default_rng(0)
    for i, arch in enumerate(ARCHS):
        v = data[arch]
        maes = [r["leap_mae"] for r in v]
        jitter = rng.uniform(-0.12, 0.12, size=len(maes))
        colors = ["#1baf7a" if r["leap_safe"] else "#e34948" for r in v]
        axS.scatter(np.full(len(maes), i) + jitter, maes, c=colors, s=70, zorder=3,
                    edgecolors="white", linewidths=0.8)
        axS.scatter([i], [statistics.mean(maes)], marker="D", s=90, color=ARCH_COLORS[arch],
                    edgecolors="black", linewidths=1.0, zorder=4)

    axS.axhline(ACCEPT_THRESH_C, color="#333333", linestyle="--", linewidth=1.2, zorder=1)
    axS.text(2.35, ACCEPT_THRESH_C + 0.25, "10°C threshold", fontsize=8.5, color="#333333", ha="right")
    axS.set_xticks(range(len(ARCHS)))
    axS.set_xticklabels([ARCH_LABELS[a] for a in ARCHS])
    axS.set_ylabel("Leap window MAE (°C)")
    axS.set_title("Per-seed leap MAE (green=SAFE, red=UNSAFE, diamond=mean)", fontsize=11, fontweight="bold")
    axS.spines[["top", "right"]].set_visible(False)
    axS.set_xlim(-0.5, 2.5)

    x = np.arange(len(ARCHS))
    eps_mean = [statistics.mean([r["leap_epochs"] for r in data[a]]) for a in ARCHS]
    eps_std = [statistics.stdev([r["leap_epochs"] for r in data[a]]) for a in ARCHS]
    bars = axE.bar(x, eps_mean, yerr=eps_std, capsize=4, color=[ARCH_COLORS[a] for a in ARCHS], width=0.55)
    axE.bar_label(bars, fmt="%.0f", fontsize=9, padding=6)
    axE.set_xticks(x)
    axE.set_xticklabels([ARCH_LABELS[a] for a in ARCHS])
    axE.set_ylabel("Leap window epochs used (mean ± std)")
    axE.set_title("Training cost of the single-leap window", fontsize=11, fontweight="bold")
    axE.spines[["top", "right"]].set_visible(False)
    axE.set_ylim(top=axE.get_ylim()[1] * 1.15)

    fig.suptitle(
        "NAS-PINN Single-Leap Experiment — Rectangle 2D, Live FEniCS FEM Reference (10-seed sweep)",
        fontsize=15, fontweight="bold", y=0.985,
    )

    out_path = FIGURES_DIR / "single_leap_table.png"
    fig.savefig(out_path, dpi=170, bbox_inches="tight", facecolor="white")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
