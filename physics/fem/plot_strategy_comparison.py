"""
3 strateji karşılaştırması: FEM-anchored (best k) vs Adaptive-k vs PINN-only
Çalıştır: python3 thermal_pinn/physics/fem/plot_strategy_comparison.py
"""

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

CKPT = Path("thermal_pinn/checkpoints")
OUT  = Path("thermal_pinn/assets/fem/strategy_comparison.png")
OUT.parent.mkdir(parents=True, exist_ok=True)

# ── Best-k seçimi ─────────────────────────────────────────────────────────────
BEST_K = {"rectangle": 1, "circle": 4, "lshape": 5}

DOMAIN_LABELS = {
    "rectangle": "Rectangle  (1.3×0.6 m)",
    "circle":    "Circle  (R=0.3 m)",
    "lshape":    "L-shape  (2×2 m)",
}

COLORS = {
    "fem":      "#1f77b4",   # blue
    "adaptive": "#ff7f0e",   # orange
    "pinn":     "#d62728",   # red
}

def load_windows(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)["windows"]

def windows_to_time_mae(windows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    t   = np.array([w["t_end"]  for w in windows])
    mae = np.array([w["mae_C"]  for w in windows])
    return t, mae

def mean_mae(windows: list[dict]) -> float:
    return float(np.mean([w["mae_C"] for w in windows]))

# ── Data yükle ────────────────────────────────────────────────────────────────
data = {}
for domain in ("rectangle", "circle", "lshape"):
    k = BEST_K[domain]
    fem_w  = load_windows(CKPT / f"{domain}_bayesian_fem_hT_k{k}_dim2_metrics.json")
    adp_w  = load_windows(CKPT / f"{domain}_bayesian_adaptive_fem_hT_dim2_metrics.json")
    pinn_w = load_windows(CKPT / f"{domain}_bayesian_pinn_only_fem_hT_k1_dim2_metrics.json")

    # Adaptive-k: k_used per window (for schedule visualization)
    adp_k  = [w.get("k_used", 1) for w in adp_w]

    data[domain] = {
        "fem":  windows_to_time_mae(fem_w),
        "adp":  windows_to_time_mae(adp_w),
        "pinn": windows_to_time_mae(pinn_w),
        "adp_k": adp_k,
        "best_k": k,
        "mean_fem":  mean_mae(fem_w),
        "mean_adp":  mean_mae(adp_w),
        "mean_pinn": mean_mae(pinn_w),
        "n_windows_fem":  len(fem_w),
        "n_windows_adp":  len(adp_w),
    }

# ── Figure: 2 satır × 3 sütun ────────────────────────────────────────────────
# Satır 1: per-window MAE zaman serisi
# Satır 2: özet bar chart + adaptive k schedule
fig = plt.figure(figsize=(16, 9))
fig.patch.set_facecolor("white")
fig.suptitle("FEM h(T) Training — Strategy Comparison (NAS-PINN Bayesian 5×151)",
             fontsize=13, y=0.98)

gs = fig.add_gridspec(2, 3, hspace=0.40, wspace=0.32,
                      left=0.07, right=0.97, top=0.92, bottom=0.08)

for col, domain in enumerate(("rectangle", "circle", "lshape")):
    d    = data[domain]
    k    = d["best_k"]
    t_f, mae_f = d["fem"]
    t_a, mae_a = d["adp"]
    t_p, mae_p = d["pinn"]

    # ── Satır 0: MAE zaman serisi ──────────────────────────────────────────
    ax0 = fig.add_subplot(gs[0, col])
    ax0.set_facecolor("white")

    ax0.plot(t_f, mae_f, "o-", color=COLORS["fem"],      lw=1.8, ms=4,
             label=f"FEM-anchored k={k}  (mean {d['mean_fem']:.1f}°C)")
    ax0.plot(t_a, mae_a, "s--", color=COLORS["adaptive"], lw=1.8, ms=4,
             label=f"Adaptive-k  (mean {d['mean_adp']:.1f}°C)")
    ax0.plot(t_p, mae_p, "^:", color=COLORS["pinn"],     lw=1.8, ms=4,
             label=f"PINN-only  (mean {d['mean_pinn']:.1f}°C)")

    ax0.set_title(DOMAIN_LABELS[domain], fontsize=10, fontweight="bold")
    ax0.set_xlabel("t [s]", fontsize=9)
    ax0.set_ylabel("MAE [°C]", fontsize=9)
    ax0.set_xlim(0, 31)
    ax0.tick_params(labelsize=8)
    ax0.legend(fontsize=7.5, loc="upper left", framealpha=0.85)
    ax0.grid(True, alpha=0.3, lw=0.6)
    ax0.axhline(15, color="gray", lw=0.8, ls="--", alpha=0.5)   # 15°C eşiği
    ax0.text(30.5, 15, "15°C", fontsize=7, color="gray", va="center")

    # ── Satır 1: Bar + adaptive k schedule ─────────────────────────────────
    ax1 = fig.add_subplot(gs[1, col])
    ax1.set_facecolor("white")

    # Sol: mean MAE barlar
    strategies = ["FEM-anchored\nk=" + str(k), "Adaptive-k", "PINN-only"]
    means      = [d["mean_fem"], d["mean_adp"], d["mean_pinn"]]
    colors_bar = [COLORS["fem"], COLORS["adaptive"], COLORS["pinn"]]
    bars = ax1.bar(strategies, means, color=colors_bar, width=0.5, alpha=0.85)
    for bar, v in zip(bars, means):
        ax1.text(bar.get_x() + bar.get_width() / 2, v + 0.5,
                 f"{v:.1f}°C", ha="center", va="bottom", fontsize=8, fontweight="bold")

    ax1.set_ylabel("Mean MAE [°C]", fontsize=9)
    ax1.set_ylim(0, max(means) * 1.22)
    ax1.tick_params(labelsize=8)
    ax1.grid(axis="y", alpha=0.3, lw=0.6)

    # FEM tasarrufu annotation
    fem_save  = (1 - d["n_windows_fem"]  / 20) * 100
    adp_save  = (1 - d["n_windows_adp"]  / 20) * 100
    ax1.set_title(
        f"FEM savings — anchored: {fem_save:.0f}%  adaptive: {adp_save:.0f}%",
        fontsize=8, color="#555555"
    )

    # Adaptive k schedule (ticks bölgesinin altında)
    adp_t   = np.array([w["t_start"] for w in
                         json.load(open(CKPT / f"{domain}_bayesian_adaptive_fem_hT_dim2_metrics.json"))["windows"]])
    adp_ks  = d["adp_k"]
    ax1b = ax1.twinx()
    ax1b.step(np.append(adp_t, 30), adp_ks + [adp_ks[-1]],
              where="post", color=COLORS["adaptive"], lw=1.2, ls="--", alpha=0.6)
    ax1b.set_ylabel("Adaptive k", fontsize=7.5, color=COLORS["adaptive"])
    ax1b.set_ylim(0, 6)
    ax1b.set_yticks([1, 2, 3, 4, 5])
    ax1b.tick_params(labelsize=7, colors=COLORS["adaptive"])

# ── Legend (ortak) ────────────────────────────────────────────────────────────
patches = [
    mpatches.Patch(color=COLORS["fem"],      label="FEM-anchored (best fixed k)"),
    mpatches.Patch(color=COLORS["adaptive"], label="Adaptive-k  (k_init=1)"),
    mpatches.Patch(color=COLORS["pinn"],     label="PINN-only  (no FEM per window)"),
]
fig.legend(handles=patches, loc="lower center", ncol=3,
           fontsize=9, framealpha=0.9, bbox_to_anchor=(0.5, 0.01))

plt.savefig(OUT, dpi=150, facecolor="white", bbox_inches="tight")
print(f"Gorsel kaydedildi: {OUT}")
