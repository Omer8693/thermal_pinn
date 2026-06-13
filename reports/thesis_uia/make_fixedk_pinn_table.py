"""
Compact slide table: Fixed-k (k=1..5) + PINN-only MAE comparison
for all 4 2D adaptive-k domains.

Output: Figures/fixedk_pinn_comparison.png
Run:    python make_fixedk_pinn_table.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

OUT = "Figures/fixedk_pinn_comparison.png"

# ── Data (seed 0, from adaptive_k_metrics.json) ───────────────────────────────
#                  Square   Circle   L-Shape  Flower
FIXED = {
    "k=1 (67% FEM saved)":  [1.39,  1.30,  1.09,  1.59],
    "k=2 (83% FEM saved)":  [7.07,  6.53,  3.21,  8.55],
    "k=3 (88% FEM saved)":  [15.53, 14.24, 7.64,  18.77],
    "k=4 (92% FEM saved)":  [24.21, 24.46, 13.59, 27.43],
    "k=5 (93% FEM saved)":  [35.22, 34.53, 20.89, 37.22],
    "PINN-only (no FEM)":   [29.6,  None,  None,  None],
}

DOMAINS = ["Square", "Circle", "L-Shape", "Flower"]

GOOD = "#C8E6C9"   # green  — MAE < 3°C
WARN = "#FFF9C4"   # yellow — 3–15°C
BAD  = "#FFCDD2"   # red    — ≥ 15°C
NA   = "#F5F5F5"   # grey   — not measured
HEAD_COL = "#1A5C96"

def bg(v):
    if v is None: return NA
    if v < 3.0:   return GOOD
    if v < 15.0:  return WARN
    return BAD

def fmt(v):
    return f"{v:.2f}" if v is not None else "—"

# ── Build rows ────────────────────────────────────────────────────────────────
row_labels = list(FIXED.keys())
cell_text   = [[fmt(v) for v in FIXED[r]] for r in row_labels]
cell_colors = [[bg(v)  for v in FIXED[r]] for r in row_labels]

# ── Figure ────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(7.5, 3.2))
ax.axis("off")
fig.patch.set_facecolor("white")

fig.suptitle("Fixed-$k$ and PINN-only: MAE (°C) — seed 0",
             fontsize=11, fontweight="bold", y=1.01)

tbl = ax.table(
    cellText=cell_text,
    rowLabels=row_labels,
    colLabels=DOMAINS,
    cellColours=cell_colors,
    rowColours=[HEAD_COL] * len(row_labels),
    colColours=[HEAD_COL] * len(DOMAINS),
    cellLoc="center",
    loc="center",
)
tbl.auto_set_font_size(False)
tbl.set_fontsize(9.5)
tbl.scale(1, 1.6)

# Header text white + bold
for j in range(len(DOMAINS)):
    tbl[0, j].set_text_props(color="white", fontweight="bold")
for i, label in enumerate(row_labels):
    tbl[i + 1, -1].set_text_props(color="white", fontsize=9)
    if "PINN" in label:
        tbl[i + 1, -1].set_facecolor("#B71C1C")
        tbl[i + 1, -1].set_text_props(color="white", fontweight="bold", fontsize=9)

# Legend
patches = [
    mpatches.Patch(color=GOOD, label="< 3 °C  ✓ good"),
    mpatches.Patch(color=WARN, label="3–15 °C  marginal"),
    mpatches.Patch(color=BAD,  label="≥ 15 °C  ✗ unacceptable"),
    mpatches.Patch(color=NA,   label="not tested"),
]
ax.legend(handles=patches, loc="lower center", ncol=4,
          fontsize=8, frameon=False,
          bbox_to_anchor=(0.5, -0.18))

plt.tight_layout()
fig.savefig(OUT, dpi=180, bbox_inches="tight", facecolor="white")
plt.close()
print(f"Saved → {OUT}")
