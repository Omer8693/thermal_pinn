"""
Generate runtime_mae_dual.png — MAE and Training Time vs FEM Call Reduction.
Shows 2D Rectangle domain, all three NAS architectures.
Run from repo root:  python thermal_pinn/reports/thesis_uia/make_runtime_mae_dual.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import json
from pathlib import Path

CKPT  = Path("thermal_pinn/checkpoints")
OUT   = Path("thermal_pinn/reports/thesis_uia/Figures/runtime_mae_dual.png")

DOMAIN = "rectangle"
DIM    = 2
K_VALS = [1, 2, 3, 4, 5]
FEM_SAVINGS = {1: "0%", 2: "50%", 3: "65%", 4: "75%", 5: "80%"}
THRESHOLD   = 10.0   # °C

ARCHS = ["bayesian", "nsga2", "nsga3"]
ARCH_LABELS  = {"bayesian": "Bayesian/TPE", "nsga2": "NSGA-II", "nsga3": "NSGA-III"}
ARCH_COLORS  = {"bayesian": "#1565C0",      "nsga2": "#E65100",  "nsga3": "#2E7D32"}
ARCH_MARKERS = {"bayesian": "o",             "nsga2": "s",        "nsga3": "^"}

# ── Load data ────────────────────────────────────────────────────────────────
data = {arch: {"mae": [], "runtime": [], "k": []} for arch in ARCHS}

for arch in ARCHS:
    for k in K_VALS:
        p = CKPT / f"{DOMAIN}_{arch}_k{k}_dim{DIM}_metrics.json"
        if not p.exists():
            continue
        m = json.loads(p.read_text())
        total_rt = sum(w["runtime_s"] for w in m["windows"])
        data[arch]["k"].append(k)
        data[arch]["mae"].append(m["mean_mae"])
        data[arch]["runtime"].append(total_rt)

# ── Plot ─────────────────────────────────────────────────────────────────────
fig, ax_mae = plt.subplots(figsize=(8.2, 5.8))
fig.patch.set_facecolor("white")
ax_mae.set_facecolor("white")

ax_rt = ax_mae.twinx()
ax_rt.set_facecolor("white")

x_positions = list(range(len(K_VALS)))
x_labels    = [f"k={k}\n({FEM_SAVINGS[k]})" for k in K_VALS]

for arch in ARCHS:
    d   = data[arch]
    ks  = d["k"]
    xs  = [K_VALS.index(k) for k in ks]
    col = ARCH_COLORS[arch]
    mk  = ARCH_MARKERS[arch]

    ax_mae.plot(xs, d["mae"],     color=col, marker=mk, lw=2.0, ms=7,
                linestyle="solid",  zorder=4)
    ax_rt.plot( xs, d["runtime"], color=col, marker=mk, lw=1.8, ms=6,
                linestyle="dashed", zorder=3, alpha=0.75)

# threshold
ax_mae.axhline(THRESHOLD, color="#C62828", lw=1.4, ls="dotted", zorder=2)

ax_mae.set_xticks(x_positions)
ax_mae.set_xticklabels(x_labels, fontsize=9)
ax_mae.set_xlabel("FEM Call Reduction (%)", fontsize=10, labelpad=10)
ax_mae.set_ylabel("Mean-Window MAE [°C]",      fontsize=10, color="#1e293b")
ax_rt.set_ylabel("Total PINN Training Time [s]", fontsize=10, color="#475569")

ax_mae.tick_params(axis="y", labelcolor="#1e293b")
ax_rt.tick_params(axis="y",  labelcolor="#475569")

ax_mae.yaxis.grid(True, linestyle="--", alpha=0.35, zorder=0)
ax_mae.set_axisbelow(True)

for sp in ax_mae.spines.values():
    sp.set_linewidth(0.8)
    sp.set_color("#94a3b8")
for sp in ax_rt.spines.values():
    sp.set_linewidth(0.8)
    sp.set_color("#94a3b8")

ax_mae.set_title(
    "MAE and Training Time vs FEM Call Reduction\n"
    f"2D Rectangle Domain, Three NAS Architectures",
    fontsize=11, fontweight="bold", pad=8, color="#0f172a",
)

# Full legend: 3 archs × 2 styles (MAE solid, Time dashed) + threshold
from matplotlib.lines import Line2D
legend_entries = []
for arch in ARCHS:
    col = ARCH_COLORS[arch]
    mk  = ARCH_MARKERS[arch]
    lbl = ARCH_LABELS[arch]
    legend_entries.append(
        Line2D([0], [0], color=col, lw=2.0, ls="solid",  marker=mk, ms=6,
               label=f"{lbl} — MAE [°C]"))
    legend_entries.append(
        Line2D([0], [0], color=col, lw=1.8, ls="dashed", marker=mk, ms=5,
               alpha=0.75, label=f"{lbl} — Training time [s]"))
legend_entries.append(
    Line2D([0], [0], color="#C62828", lw=1.4, ls="dotted",
           label=f"{THRESHOLD:.0f}°C MAE threshold"))

fig.legend(handles=legend_entries,
           loc="lower center", ncol=2, fontsize=8.2,
           framealpha=0.95, edgecolor="#cbd5e1",
           bbox_to_anchor=(0.5, 0.025))

fig.tight_layout(rect=[0, 0.30, 1, 0.96])
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=180, facecolor="white", edgecolor="none")
plt.close(fig)
print(f"Saved → {OUT}")
