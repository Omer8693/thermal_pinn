"""
MAE vs k-sweep plot for 3D domains.
Run: python make_3d_ksweep.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import json
from pathlib import Path

BASE = Path("../../checkpoints")
OUT  = Path("Figures/3d_kskip_mae.png")

DOMAINS = ["rectangular", "cylinder", "stacked", "lshape"]
DLABELS = {"rectangular": "Rectangular", "cylinder": "Cylinder",
           "stacked": "Stacked", "lshape": "L-shape 3D"}
ARCHS  = ["bayesian", "nsga2", "nsga3"]
ALABELS = {"bayesian": "Bayesian/TPE", "nsga2": "NSGA-II", "nsga3": "NSGA-III"}
ACOLORS = {"bayesian": "#1A5C96", "nsga2": "#C62828", "nsga3": "#2E7D32"}
AMARKERS= {"bayesian": "o", "nsga2": "s", "nsga3": "^"}
K_VALS = [1, 2, 3, 4, 5]
FEM_SAVINGS = {1:"0%", 2:"50%", 3:"65%", 4:"75%", 5:"80%"}

reg = json.loads((BASE / "registry.json").read_text())

fig, axes = plt.subplots(1, 4, figsize=(18, 4.5), sharey=False)
fig.suptitle("Mean MAE vs Skip Factor $k$ — 3D Benchmark Domains",
             fontsize=13, fontweight="bold")

for ax, domain in zip(axes, DOMAINS):
    for arch in ARCHS:
        entries = [r for r in reg
                   if r['domain']==domain and r['arch']==arch and r['dim']==3]
        if not entries: continue
        e = entries[0]
        all_k = e.get('all_k', {})
        k_plot = [k for k in K_VALS if str(k) in all_k]
        m_plot = [all_k[str(k)] for k in k_plot]
        if not k_plot: continue

        ax.plot(k_plot, m_plot,
                color=ACOLORS[arch], marker=AMARKERS[arch],
                lw=2.0, ms=8, zorder=3, label=ALABELS[arch])

        best_k = e['best_k']
        best_mae = e['best_mae']
        ax.scatter([best_k], [best_mae], marker="*",
                   s=180, color=ACOLORS[arch],
                   edgecolors="gold", linewidths=1.5, zorder=5)

    ax.set_title(DLABELS[domain], fontsize=11, fontweight="bold")
    ax.set_xlabel("$k$ (skip factor)", fontsize=10)
    ax.set_ylabel("Mean MAE [°C]", fontsize=10)
    ax.set_xticks(K_VALS)
    ax.set_xticklabels([f"k={k}\n({FEM_SAVINGS[k]})" for k in K_VALS], fontsize=8)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.set_ylim(bottom=0)

    if domain == DOMAINS[0]:
        ax.legend(fontsize=9, loc="upper left")

fig.text(0.5, 0.01, "★ = best $k$ per architecture   |   dashed = data not available",
         ha="center", fontsize=9, color="#555", style="italic")

plt.tight_layout(rect=[0, 0.04, 1, 1])
OUT.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(OUT, dpi=180, bbox_inches="tight", facecolor="white")
print(f"Saved → {OUT}")
