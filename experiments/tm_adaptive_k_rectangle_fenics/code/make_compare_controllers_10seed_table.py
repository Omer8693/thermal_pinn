"""
experiments/tm_adaptive_k_rectangle_fenics/make_compare_controllers_10seed_table.py
====================================================================================
Comprehensive PNG report for the 10-seed compare_controllers.py sweep
(seeds 42-51, 3 architectures, Rectangle 2D, live FEniCS) - Algorithm 3
(PINN) vs TM-guided (PINN+TM) vs TM-hybrid (PINN+TM-hybrid).

Reads reports/compare_controllers{,_nsga2,_nsga3}[_seed{43..51}].json and
renders:
  (A) a comprehensive results table with mean +/- std across the 10 seeds -
      windows/steps, FEM savings, mean/max MAE, unsafe-window rate (both
      per-window and per-seed), total runtime.
  (B) grouped bar charts with error bars (std across seeds) - FEM windows
      and total runtime, one group per architecture, one bar per controller.

Run after compare_controllers.py has been run for seeds 42-51 x
{bayesian, nsga2, nsga3}.
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

ARCHS = ["bayesian", "nsga2", "nsga3"]
ARCH_LABELS = {"bayesian": "Bayesian/TPE", "nsga2": "NSGA-II", "nsga3": "NSGA-III"}
CONTROLLERS = ["algorithm3", "tm_guided", "tm_hybrid"]
CONTROLLER_LABELS = {"algorithm3": "PINN", "tm_guided": "PINN+TM", "tm_hybrid": "PINN+TM-hybrid"}
CONTROLLER_COLORS = {"algorithm3": "#2a78d6", "tm_guided": "#eb6834", "tm_hybrid": "#1baf7a"}
SEEDS = list(range(42, 52))


def fname(arch: str, seed: int) -> Path:
    tag = "" if arch == "bayesian" else f"_{arch}"
    if seed != 42:
        tag += f"_seed{seed}"
    return REPORTS_DIR / f"compare_controllers{tag}.json"


def load_all():
    out = {}
    for arch in ARCHS:
        out[arch] = {}
        for ctrl in CONTROLLERS:
            windows, savings, mean_mae, max_mae, unsafe_win, unsafe_seed, runtime = [], [], [], [], [], [], []
            mean_l2, max_l2 = [], []
            for seed in SEEDS:
                d = json.load(open(fname(arch, seed)))
                c = d[ctrl]
                n_unsafe = sum(1 for w in c["windows"] if w["true_label"] == "UNSAFE")
                l2s = [w["l2_rel"] for w in c["windows"]]
                windows.append(c["n_windows"])
                savings.append(c["fem_savings_pct"])
                mean_mae.append(c["mean_mae"])
                max_mae.append(c["max_mae"])
                unsafe_win.append(n_unsafe)
                unsafe_seed.append(1 if n_unsafe > 0 else 0)
                runtime.append(c["total_s"])
                mean_l2.append(statistics.mean(l2s))
                max_l2.append(max(l2s))
            out[arch][ctrl] = dict(windows=windows, savings=savings, mean_mae=mean_mae,
                                    max_mae=max_mae, unsafe_win=unsafe_win,
                                    unsafe_seed=unsafe_seed, runtime=runtime,
                                    mean_l2=mean_l2, max_l2=max_l2)
    return out


def m(v):
    return statistics.mean(v)


def s(v):
    return statistics.stdev(v) if len(v) > 1 else 0.0


def safety_color(unsafe_seed_count):
    if unsafe_seed_count == 0:
        return "#dbe9f7"
    if unsafe_seed_count <= 3:
        return "#fde3b8"
    return "#f6c9c0"


def main():
    data = load_all()

    fig = plt.figure(figsize=(19.5, 14), facecolor="white")
    gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 0.62], hspace=0.16, top=0.93, bottom=0.05,
                           left=0.02, right=0.98)

    # -----------------------------------------------------------------
    # Panel A: comprehensive table, mean +/- std over 10 seeds
    # -----------------------------------------------------------------
    axA = fig.add_subplot(gs[0])
    axA.axis("off")
    axA.set_title(
        f"Adaptive-k controller comparison — Rectangle 2D, live FEniCS, {len(SEEDS)}-seed sweep (seeds {SEEDS[0]}-{SEEDS[-1]})\n"
        "Algorithm 3 (PINN)  vs  TM-guided (PINN+TM)  vs  TM-hybrid (PINN+TM-hybrid) — mean ± std across seeds",
        fontsize=13.5, fontweight="bold", pad=10,
    )

    col_labels = ["Architecture", "Controller", "Windows\n(FEM calls)", "FEM\nsavings",
                  "Mean MAE\n(°C)", "Max MAE\n(°C)", "Mean L2 rel\nerror", "Max L2 rel\nerror",
                  "Unsafe windows\n(total / seeds affected)", "Total runtime (s)"]
    rows, unsafe_seed_counts, ctrl_keys = [], [], []
    for arch in ARCHS:
        for ctrl in CONTROLLERS:
            v = data[arch][ctrl]
            n_unsafe_seeds = sum(v["unsafe_seed"])
            rows.append([
                ARCH_LABELS[arch], CONTROLLER_LABELS[ctrl],
                f"{m(v['windows']):.1f}±{s(v['windows']):.1f}",
                f"{m(v['savings']):.1f}%",
                f"{m(v['mean_mae']):.2f}±{s(v['mean_mae']):.2f}",
                f"{m(v['max_mae']):.2f}±{s(v['max_mae']):.2f}",
                f"{m(v['mean_l2']):.4f}±{s(v['mean_l2']):.4f}",
                f"{m(v['max_l2']):.4f}±{s(v['max_l2']):.4f}",
                f"{sum(v['unsafe_win'])}/{sum(v['windows'])}  ({n_unsafe_seeds}/{len(SEEDS)} seeds)",
                f"{m(v['runtime']):.0f}±{s(v['runtime']):.0f}",
            ])
            unsafe_seed_counts.append(n_unsafe_seeds)
            ctrl_keys.append(ctrl)

    table = axA.table(cellText=rows, colLabels=col_labels, cellLoc="center",
                       bbox=[0.0, 0.06, 1.0, 0.84],
                       colWidths=[0.115, 0.13, 0.1, 0.08, 0.115, 0.115, 0.1, 0.1, 0.16, 0.1])
    table.auto_set_font_size(False)
    table.set_fontsize(9.8)
    for j in range(len(col_labels)):
        table[0, j].set_facecolor("#2c3e50")
        table[0, j].set_text_props(color="white", fontweight="bold")
    for i in range(len(rows)):
        r = i + 1
        table[r, 0].set_text_props(fontweight="bold")
        table[r, 1].set_text_props(color=CONTROLLER_COLORS[ctrl_keys[i]], fontweight="bold")
        table[r, 8].set_facecolor(safety_color(unsafe_seed_counts[i]))
        if ctrl_keys[i] == "tm_hybrid":
            table[r, 3].set_facecolor("#d5f2d5")
        if i % 3 == 0 and i > 0:
            for j in range(len(col_labels)):
                table[r, j].set_edgecolor("#888888")
                table[r, j].set_linewidth(1.4)

    axA.text(
        0.0, 0.0,
        "'Unsafe windows' colored by how many of the 10 seeds had at least one unsafe episode "
        "(light blue = 0 seeds, amber = 1-3, light red = 4+). All controllers within an architecture "
        "share the same 10 model seeds (42-51), the same live FEniCS reference, and the same starting weights per seed.",
        transform=axA.transAxes, fontsize=8.5, color="#555555", wrap=True,
    )

    # -----------------------------------------------------------------
    # Panel B: grouped bar charts with error bars — windows and runtime
    # -----------------------------------------------------------------
    gsB = gs[1].subgridspec(1, 2, wspace=0.2)
    axW = fig.add_subplot(gsB[0])
    axT = fig.add_subplot(gsB[1])

    x = np.arange(len(ARCHS))
    width = 0.26
    for i, ctrl in enumerate(CONTROLLERS):
        offset = (i - 1) * width
        color = CONTROLLER_COLORS[ctrl]
        w_means = [m(data[a][ctrl]["windows"]) for a in ARCHS]
        w_stds = [s(data[a][ctrl]["windows"]) for a in ARCHS]
        t_means = [m(data[a][ctrl]["runtime"]) for a in ARCHS]
        t_stds = [s(data[a][ctrl]["runtime"]) for a in ARCHS]
        bw = axW.bar(x + offset, w_means, width, yerr=w_stds, capsize=3,
                     label=CONTROLLER_LABELS[ctrl], color=color)
        bt = axT.bar(x + offset, t_means, width, yerr=t_stds, capsize=3,
                     label=CONTROLLER_LABELS[ctrl], color=color)
        axW.bar_label(bw, fmt="%.1f", fontsize=7.5, padding=8)
        axT.bar_label(bt, fmt="%.0f", fontsize=7.5, padding=8)

    axW.axhline(20, color="#999999", linestyle="--", linewidth=1, zorder=0)
    axW.text(-0.42, 20.4, "k=1 baseline (20)", fontsize=7.5, color="#777777", ha="left")
    axW.set_xticks(x)
    axW.set_xticklabels([ARCH_LABELS[a] for a in ARCHS])
    axW.set_ylabel("FEM windows (steps)")
    axW.set_title("Steps to complete the 30 s cooling curve (mean ± std, 10 seeds)", fontsize=10.5, fontweight="bold")
    axW.spines[["top", "right"]].set_visible(False)
    axW.legend(fontsize=8.5, frameon=False, loc="upper right")

    axT.set_xticks(x)
    axT.set_xticklabels([ARCH_LABELS[a] for a in ARCHS])
    axT.set_ylabel("Total wall-clock runtime (s)")
    axT.set_title("Runtime to complete the 30 s cooling curve (mean ± std, 10 seeds)", fontsize=10.5, fontweight="bold")
    axT.spines[["top", "right"]].set_visible(False)
    axT.set_ylim(top=axT.get_ylim()[1] * 1.12)
    axT.legend(fontsize=8.5, frameon=False, loc="upper left")

    fig.suptitle(
        "NAS-PINN + Adaptive-k + Tsetlin Machine — Rectangle 2D, Live FEniCS FEM Reference (10-seed sweep)",
        fontsize=15, fontweight="bold", y=0.985,
    )

    out_path = FIGURES_DIR / "compare_controllers_10seed_table.png"
    fig.savefig(out_path, dpi=170, bbox_inches="tight", facecolor="white")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
