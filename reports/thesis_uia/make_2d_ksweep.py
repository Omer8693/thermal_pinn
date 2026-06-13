"""
Generate MAE vs k-sweep plot for 2D domains.
Run: python make_2d_ksweep.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import json
from pathlib import Path

BASE  = Path("../../checkpoints")
OUT   = Path("Figures/2d_kskip_mae.png")

DOMAINS = ["rectangle", "circle", "lshape"]
DOMAIN_LABELS = {"rectangle": "Rectangle", "circle": "Circle", "lshape": "L-shape"}
ARCHS  = ["bayesian", "nsga2", "nsga3"]
ARCH_LABELS = {"bayesian": "Bayesian/TPE", "nsga2": "NSGA-II", "nsga3": "NSGA-III"}
ARCH_COLORS = {"bayesian": "#1A5C96", "nsga2": "#C62828", "nsga3": "#2E7D32"}
ARCH_MARKERS= {"bayesian": "o", "nsga2": "s", "nsga3": "^"}
K_VALS = [1, 2, 3, 4, 5]
FEM_SAVINGS = {1: "0%", 2: "50%", 3: "65%", 4: "75%", 5: "80%"}

reg = json.loads((BASE / "registry.json").read_text())

fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=False)
fig.suptitle("Mean MAE vs Skip Factor $k$ — 2D Benchmark Domains",
             fontsize=13, fontweight="bold")

for ax, domain in zip(axes, DOMAINS):
    for arch in ARCHS:
        entries = [r for r in reg
                   if r['domain']==domain and r['arch']==arch and r['dim']==2]
        if not entries: continue
        e = entries[0]
        all_k = e.get('all_k', {})
        maes = [all_k.get(str(k), None) for k in K_VALS]
        k_plot = [k for k, m in zip(K_VALS, maes) if m is not None]
        m_plot = [m for m in maes if m is not None]

        ax.plot(k_plot, m_plot,
                color=ARCH_COLORS[arch],
                marker=ARCH_MARKERS[arch],
                lw=2.0, ms=8, zorder=3,
                label=ARCH_LABELS[arch])

        # Mark best k with star
        best_k = e['best_k']
        best_mae = e['best_mae']
        ax.scatter([best_k], [best_mae], marker="*",
                   s=180, color=ARCH_COLORS[arch],
                   edgecolors="gold", linewidths=1.5, zorder=5)

    ax.set_title(DOMAIN_LABELS[domain], fontsize=12, fontweight="bold")
    ax.set_xlabel("$k$ (skip factor)", fontsize=10)
    ax.set_ylabel("Mean MAE [°C]", fontsize=10)
    ax.set_xticks(K_VALS)
    ax.set_xticklabels([f"k={k}\n({FEM_SAVINGS[k]})" for k in K_VALS], fontsize=8)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.set_ylim(bottom=0)

    if domain == DOMAINS[0]:
        ax.legend(fontsize=9, loc="upper left")

# Shared star explanation
fig.text(0.5, 0.01, "★ = best $k$ per architecture",
         ha="center", fontsize=9, color="#555", style="italic")

plt.tight_layout(rect=[0, 0.04, 1, 1])
OUT.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(OUT, dpi=180, bbox_inches="tight", facecolor="white")
print(f"Saved → {OUT}")
