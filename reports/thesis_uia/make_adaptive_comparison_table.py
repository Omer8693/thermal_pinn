"""
Generates a slide-ready comparison figure:
  Fixed-k (k=1..5) vs Adaptive-k (NAS Transfer + Bayesian/TPE) vs PINN-only
  for the four 2D adaptive-k domains (Square, Circle, L-Shape, Flower).

Output: Figures/adaptive_k_comparison_table.png

Run from the thesis_uia directory:
    python make_adaptive_comparison_table.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

OUT = Path("Figures/adaptive_k_comparison_table.png")
OUT.parent.mkdir(parents=True, exist_ok=True)

# ── Data ──────────────────────────────────────────────────────────────────────
# Seed-0 values from adaptive_k_metrics.json (verified against raw data)
DOMAINS = ["Square", "Circle", "L-Shape", "Flower"]

# [k=1, k=2, k=3, k=4, k=5]
FIXED = {
    "Square":  [1.39, 7.07, 15.53, 24.21, 35.22],
    "Circle":  [1.30, 6.53, 14.24, 24.46, 34.53],
    "L-Shape": [1.09, 3.21,  7.64, 13.59, 20.89],
    "Flower":  [1.59, 8.55, 18.77, 27.43, 37.22],
}
FIXED_FEM = [67, 83, 88, 92, 93]   # % FEM saved per k

ADAPTIVE = {
    #              NAS Transfer   Bayesian/TPE (seed0)
    "Square":  [1.66,  1.52],
    "Circle":  [1.48,  1.43],
    "L-Shape": [2.38,  1.37],
    "Flower":  [2.01,  1.62],
}
ADAPTIVE_FEM = 85  # % FEM saved

PINN_ONLY = {"Square": 29.6}   # only Square preliminary; others not available

MAE_ACCEPT = 15.0   # engineering threshold

# ── Colour scheme (same as other thesis figures) ──────────────────────────────
C_BLUE   = "#1A5C96"   # Bayesian/TPE
C_RED    = "#C62828"   # fixed-k danger
C_GREEN  = "#2E7D32"   # NAS Transfer
C_ORANGE = "#E65100"   # PINN-only
C_GREY   = "#607D8B"   # neutral

GOOD  = "#E8F5E9"   # light green bg
WARN  = "#FFF9C4"   # light yellow bg
BAD   = "#FFEBEE"   # light red bg
HEAD  = "#E3F2FD"   # header blue bg

def cell_color(mae):
    if mae < 3.0:  return GOOD
    if mae < MAE_ACCEPT: return WARN
    return BAD

def fmt(mae):
    return f"{mae:.2f}"

# ── Build table data ──────────────────────────────────────────────────────────
col_labels = [
    "Configuration", "FEM saved",
    "Square", "Circle", "L-Shape", "Flower",
]

rows = []
row_colors = []

# Fixed k=1
row = ["Fixed k=1 (no adapt.)", "67%"] + [fmt(FIXED[d][0]) for d in DOMAINS]
rows.append(row)
row_colors.append([HEAD, HEAD] + [cell_color(FIXED[d][0]) for d in DOMAINS])

# Fixed k=2..5
for i, k in enumerate(range(2, 6)):
    row = [f"Fixed k={k} (no adapt.)", f"{FIXED_FEM[i+1]}%"] + [fmt(FIXED[d][i+1]) for d in DOMAINS]
    rows.append(row)
    row_colors.append([HEAD, HEAD] + [cell_color(FIXED[d][i+1]) for d in DOMAINS])

# Separator row (blank)
rows.append([""] * 6)
row_colors.append(["white"] * 6)

# NAS Transfer adaptive
row = ["Adaptive-k  NAS Transfer", f"{ADAPTIVE_FEM}%"] + [fmt(ADAPTIVE[d][0]) for d in DOMAINS]
rows.append(row)
row_colors.append([HEAD, HEAD] + [cell_color(ADAPTIVE[d][0]) for d in DOMAINS])

# Bayesian adaptive
row = ["Adaptive-k  Bayesian/TPE", f"{ADAPTIVE_FEM}%"] + [fmt(ADAPTIVE[d][1]) for d in DOMAINS]
rows.append(row)
row_colors.append([HEAD, HEAD] + [cell_color(ADAPTIVE[d][1]) for d in DOMAINS])

# Separator
rows.append([""] * 6)
row_colors.append(["white"] * 6)

# PINN-only
row = ["PINN-only (no FEM at all)", "100%",
       fmt(PINN_ONLY["Square"]), "—", "—", "—"]
rows.append(row)
row_colors.append([HEAD, HEAD, BAD, "#F5F5F5", "#F5F5F5", "#F5F5F5"])

# ── Figure ────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(13, 5.6))
ax.axis("off")

fig.patch.set_facecolor("white")
fig.suptitle(
    "2D Adaptive-$k$: Fixed-k vs Adaptive-k vs PINN-only  —  MAE (°C), seed 0",
    fontsize=13, fontweight="bold", y=0.98,
)

col_widths = [0.28, 0.10, 0.155, 0.155, 0.155, 0.155]

tbl = ax.table(
    cellText=rows,
    colLabels=col_labels,
    cellColours=row_colors,
    colWidths=col_widths,
    loc="center",
    cellLoc="center",
)
tbl.auto_set_font_size(False)
tbl.set_fontsize(10)
tbl.scale(1, 1.55)

# Style header row
for j in range(len(col_labels)):
    cell = tbl[0, j]
    cell.set_facecolor(C_BLUE)
    cell.set_text_props(color="white", fontweight="bold", fontsize=10)

# Bold the "Configuration" column
for i in range(1, len(rows) + 1):
    cell = tbl[i, 0]
    txt = cell.get_text().get_text()
    if "Adaptive-k" in txt:
        cell.set_text_props(fontweight="bold", color=C_BLUE)
    elif "PINN-only" in txt:
        cell.set_text_props(fontweight="bold", color=C_ORANGE)
    elif "Fixed" in txt:
        cell.set_text_props(color=C_GREY)

# Bold the best MAE per domain column
best_mae = {d: min(ADAPTIVE[d][1], FIXED[d][0]) for d in DOMAINS}

# Legend patches
patches = [
    mpatches.Patch(color=GOOD,  label="MAE < 3 °C  (good)"),
    mpatches.Patch(color=WARN,  label="3 – 15 °C  (marginal)"),
    mpatches.Patch(color=BAD,   label="≥ 15 °C  (unacceptable)"),
]
ax.legend(handles=patches, loc="lower center", ncol=3,
          fontsize=9, frameon=True,
          bbox_to_anchor=(0.5, -0.04))

# Key message box
ax.text(0.5, -0.03,
    "★  Adaptive-k achieves fixed k=1 accuracy (≈1.4–2.4 °C) "
    "while saving 85% FEM calls  ·  Fixed k≥2 fails rapidly  ·  "
    "PINN-only (no FEM): 18× worse than adaptive-k on Square",
    transform=ax.transAxes, fontsize=8.5, ha="center", va="top",
    color="#1A237E", fontstyle="italic",
    bbox=dict(boxstyle="round,pad=0.3", facecolor="#E8EAF6", edgecolor="#3949AB", lw=1),
)

plt.tight_layout(rect=[0, 0.06, 1, 0.96])
fig.savefig(OUT, dpi=180, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"Saved → {OUT}")
