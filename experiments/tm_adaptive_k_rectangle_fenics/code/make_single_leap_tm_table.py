"""
experiments/tm_adaptive_k_rectangle_fenics/make_single_leap_tm_table.py
============================================================================
Comprehensive PNG table for the TM-gated single-leap experiment
(single_leap_tm_experiment.py): TM decides when the leap window (k~=19,
out-of-distribution for a classifier trained only on k<=5) is done, using
diagnostics only (no mae_C access) - contrasted against the original
train_to_best result (single_leap_table.png / true-MAE-driven plateau
search) to show the cost of trusting TM outside its training distribution.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import matplotlib.pyplot as plt

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = EXPERIMENT_ROOT / "reports" / "rectangle"
FIGURES_DIR = EXPERIMENT_ROOT / "figures" / "rectangle"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
ACCEPT_THRESH_C = 10.0
ARCHS = ["bayesian", "nsga2", "nsga3"]
ARCH_LABELS = {"bayesian": "Bayesian/TPE", "nsga2": "NSGA-II", "nsga3": "NSGA-III"}
ARCH_COLORS = {"bayesian": "#2a78d6", "nsga2": "#eb6834", "nsga3": "#1baf7a"}

# train_to_best reference (single_leap_table.png / true-MAE-driven plateau search)
REFERENCE = {
    "bayesian": {"safe": 2, "mean_epochs": 2480},
    "nsga2": {"safe": 10, "mean_epochs": 14960},
    "nsga3": {"safe": 10, "mean_epochs": 14880},
}


def m(v):
    return statistics.mean(v)


def s(v):
    return statistics.stdev(v) if len(v) > 1 else 0.0


def safety_color(n_safe):
    if n_safe >= 9:
        return "#dbe9f7"
    if n_safe >= 5:
        return "#fde3b8"
    return "#f6c9c0"


def main():
    all_runs = json.load(open(REPORTS_DIR / "single_leap_tm_sweep.json"))
    by_arch = {a: [] for a in ARCHS}
    for run in all_runs:
        by_arch[run["arch"]].append(run["windows"][1])  # leap window only

    fig = plt.figure(figsize=(20, 7.5), facecolor="white")
    ax = fig.add_subplot(111)
    ax.axis("off")
    ax.set_title(
        "TM-gated single-leap experiment — TM decides SAFE/UNSAFE from diagnostics only (no mae_C access)\n"
        "10-seed sweep (seeds 42-51), Rectangle 2D, live FEniCS — vs. true-MAE-driven train_to_best (single_leap_table.png)",
        fontsize=13, fontweight="bold", pad=10,
    )

    col_labels = ["Architecture", "TM correct\n(/10)", "False-SAFE\n(dangerous, /10)",
                  "True SAFE rate\n(TM-gated)", "Leap MAE\n(mean±std, °C)",
                  "Epochs used\n(mean,\nTM-gated)", "True SAFE rate\n(train_to_best\nreference)",
                  "Epochs\n(train_to_best\nreference)", "Verdict"]
    rows, safe_counts = [], []
    for arch in ARCHS:
        leaps = by_arch[arch]
        n = len(leaps)
        n_right = sum(1 for l in leaps if l["tm_was_right"])
        n_false_safe = sum(1 for l in leaps if l["tm_pred_final"] == "SAFE" and l["true_label"] == "UNSAFE")
        n_true_safe = sum(1 for l in leaps if l["true_label"] == "SAFE")
        maes = [l["mae_C"] for l in leaps]
        eps = [l["n_epochs_used"] for l in leaps]
        ref = REFERENCE[arch]
        if n_true_safe >= ref["safe"] - 1 and m(eps) < ref["mean_epochs"] * 0.7:
            verdict = "TM helps (much cheaper, ~same safety)"
        elif n_true_safe < ref["safe"] - 3:
            verdict = "TM UNSAFE — do not use"
        else:
            verdict = "Mixed / caution"
        rows.append([
            ARCH_LABELS[arch], f"{n_right}/{n}", f"{n_false_safe}/{n}",
            f"{n_true_safe}/{n}", f"{m(maes):.2f}±{s(maes):.2f}",
            f"{m(eps):.0f}", f"{ref['safe']}/10", f"{ref['mean_epochs']}",
            verdict,
        ])
        safe_counts.append(n_true_safe)

    table = ax.table(cellText=rows, colLabels=col_labels, cellLoc="center",
                      bbox=[0.0, 0.08, 1.0, 0.78],
                      colWidths=[0.11, 0.09, 0.12, 0.1, 0.12, 0.1, 0.11, 0.1, 0.15])
    table.auto_set_font_size(False)
    table.set_fontsize(9.8)
    for j in range(len(col_labels)):
        table[0, j].set_facecolor("#2c3e50")
        table[0, j].set_text_props(color="white", fontweight="bold")
    for i, arch in enumerate(ARCHS):
        r = i + 1
        table[r, 0].set_text_props(fontweight="bold", color=ARCH_COLORS[arch])
        table[r, 2].set_facecolor("#f6c9c0" if int(rows[i][2].split("/")[0]) >= 5 else
                                   ("#fde3b8" if int(rows[i][2].split("/")[0]) >= 1 else "#dbe9f7"))
        table[r, 3].set_facecolor(safety_color(safe_counts[i]))
        table[r, 8].set_text_props(fontweight="bold",
                                    color="#c00000" if "UNSAFE" in rows[i][8] else
                                    ("#1a6b1a" if "helps" in rows[i][8] else "#8a6d00"))

    ax.text(
        0.0, 0.02,
        "'False-SAFE' = TM told the retry loop to stop while the window was truly UNSAFE — the dangerous error, "
        "since nothing else catches it without a live FEM ground-truth check. TM was trained only on k<=5 fixed-k "
        "sweep data; the leap window is k~=19 — this experiment is an out-of-distribution generalization test, "
        "not a rerun of the original single-leap result.",
        transform=ax.transAxes, fontsize=8.5, color="#555555", wrap=True,
    )

    out_path = FIGURES_DIR / "single_leap_tm_table.png"
    fig.savefig(out_path, dpi=170, bbox_inches="tight", facecolor="white")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
