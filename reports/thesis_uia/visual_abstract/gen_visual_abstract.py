"""
Comprehensive academic visual abstract following the prescribed structure.
Layout (portrait A4-style, wide):

Row 0: Title banner
Row 1: Problem & Benchmark Geometries  (full width, split: text | thumbnails)
Row 2: FEM Reference  |  NAS-PINN Framework  |  MSWP
Row 3: Key Results (full width: trade-off plot + summary table)
Row 4: Contributions & Impact (2 text boxes)
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from pathlib import Path
import numpy as np

FIG_DIR = Path(__file__).resolve().parents[1] / "Figures"
OUT     = Path(__file__).parent

# ── Colours ────────────────────────────────────────────────────────────────────
C_HEADER  = "#1A2A4A"   # dark navy for title bars
C_BLUE    = "#2471A3"
C_GREEN   = "#1E8449"
C_ORANGE  = "#D35400"
C_TEAL    = "#148F77"
C_GREY_BG = "#F8F9FA"
C_RULE    = "#CCCCCC"
WHITE     = "white"

def title_bar(ax, text, color=C_HEADER, fs=10):
    ax.set_facecolor(color)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values(): sp.set_visible(False)
    ax.text(0.015, 0.5, text, ha="left", va="center",
            fontsize=fs, fontweight="bold", color=WHITE,
            transform=ax.transAxes)

def img_panel(ax, fname):
    path = FIG_DIR / fname
    if path.exists():
        img = mpimg.imread(str(path))
        ax.imshow(img, aspect="auto")
    ax.axis("off")
    for sp in ax.spines.values():
        sp.set_visible(True); sp.set_color(C_RULE); sp.set_linewidth(0.5)

def text_panel(ax, lines, bg=C_GREY_BG, color="#1A1A1A", fs=8.8, lh=1.6):
    ax.set_facecolor(bg)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(True); sp.set_color(C_RULE); sp.set_linewidth(0.5)
    y = 0.95
    for line in lines:
        bold = line.startswith("**") and line.endswith("**")
        txt  = line.strip("**")
        fs_  = fs + 0.5 if bold else fs
        fw   = "bold" if bold else "normal"
        col  = color if not bold else C_BLUE
        ax.text(0.04, y, txt, ha="left", va="top", fontsize=fs_,
                fontweight=fw, color=col, transform=ax.transAxes)
        y -= (fs_ + 2) / (ax.get_position().height * 1080) * lh
        if y < 0.02: break

def method_panel(ax, title, steps, color):
    ax.set_facecolor(C_GREY_BG)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(True); sp.set_color(C_RULE); sp.set_linewidth(0.5)

    ax.text(0.04, 0.90, title, ha="left", va="top",
            fontsize=12, fontweight="bold", color=color, transform=ax.transAxes)
    y = 0.70
    for i, (head, body) in enumerate(steps):
        ax.add_patch(mpatches.FancyBboxPatch(
            (0.05, y - 0.075), 0.90, 0.13,
            boxstyle="round,pad=0.012", fc="white", ec="#D2D6DA", lw=0.8,
            transform=ax.transAxes))
        ax.text(0.09, y + 0.025, head, ha="left", va="center",
                fontsize=9.5, fontweight="bold", color="#111111",
                transform=ax.transAxes)
        ax.text(0.09, y - 0.030, body, ha="left", va="center",
                fontsize=8.1, color="#333333", transform=ax.transAxes)
        if i < len(steps) - 1:
            ax.annotate("", xy=(0.50, y - 0.145), xytext=(0.50, y - 0.085),
                        arrowprops=dict(arrowstyle="-|>", lw=1.0, color=color),
                        xycoords=ax.transAxes)
        y -= 0.235

def key_results_panel(ax):
    studies = [
        ("2D adaptive-k transfer", "Square, Circle, L-Shape, Flower", 85, "MAE < 2.5°C", C_BLUE),
        ("2D canonical fixed-k", "Rectangle, Circle, L-Shape", 65, "Bayes/TPE k=3 < 5°C", C_TEAL),
        ("3D canonical fixed-k", "Rectangular, Cylinder, Stacked, L-Shape", 80, "Bayes/TPE k=5 < 14.1°C", C_GREEN),
        ("Thermal Fin fixed-k", "3D Thermal Fin benchmark", 80, "Bayes/TPE k=5 = 12.55°C", C_ORANGE),
    ]
    ax.set_facecolor(C_GREY_BG)
    for sp in ax.spines.values():
        sp.set_visible(True); sp.set_color(C_RULE); sp.set_linewidth(0.5)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([]); ax.set_yticks([])
    ax.text(0.03, 0.95, "Key result streams kept separate",
            ha="left", va="top", fontsize=11.2, fontweight="bold",
            color=C_HEADER, transform=ax.transAxes)

    label_x = 0.04
    bar_x = 0.48
    bar_w = 0.34
    y0 = 0.78
    step = 0.18
    bar_h = 0.058

    for i, (name, domains, saving, mae, color) in enumerate(studies):
        y = y0 - i * step
        ax.text(label_x, y + 0.035, name, ha="left", va="bottom",
                fontsize=9.0, fontweight="bold", color="#111111",
                transform=ax.transAxes)
        ax.text(label_x, y - 0.015, domains, ha="left", va="top",
                fontsize=7.8, color="#333333", transform=ax.transAxes)

        ax.add_patch(mpatches.Rectangle((bar_x, y - bar_h/2), bar_w, bar_h,
                                        transform=ax.transAxes, fc="#E6E8EB",
                                        ec="#D0D4D8", lw=0.5))
        fill_w = bar_w * saving / 100.0
        ax.add_patch(mpatches.Rectangle((bar_x, y - bar_h/2), fill_w, bar_h,
                                        transform=ax.transAxes, fc=color,
                                        ec="none", alpha=0.90))
        ax.text(bar_x + bar_w + 0.025, y + 0.018, f"{saving}%",
                ha="left", va="center", fontsize=9.2, fontweight="bold",
                color="#111111", transform=ax.transAxes)
        ax.text(bar_x + bar_w + 0.025, y - 0.035, mae,
                ha="left", va="center", fontsize=7.7, color="#333333",
                transform=ax.transAxes)

    ax.text(bar_x, 0.86, "FEM saving",
            ha="left", va="center", fontsize=8.6, fontweight="bold",
            color="#111111", transform=ax.transAxes)

# ── Figure ─────────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(22, 17.2), facecolor="white")

# Height ratios: [title_strip, R1_strip, R1_img, R2_strip, R2_img, R3_strip, R3_img, R4_strip, R4_img]
# Row structure: each section = thin title bar + content area
HR = [0.030,   # header
      0.026, 0.160,  # Row 1: Benchmark Geometries
      0.026, 0.380,  # Row 2: FEM | NAS-PINN | MSWP (expanded downward)
      0.026, 0.188,  # Row 3: Key Results
      0.026, 0.152,  # Row 4: Contributions, Impact, References
     ]

gs = GridSpec(len(HR), 6, figure=fig,
              left=0.01, right=0.99, top=0.98, bottom=0.01,
              wspace=0.028, hspace=0.010,
              height_ratios=HR)

# ═══════════════════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════════════════
ax_h = fig.add_subplot(gs[0, :])
ax_h.set_facecolor(C_HEADER)
ax_h.set_xticks([]); ax_h.set_yticks([])
for sp in ax_h.spines.values(): sp.set_visible(False)
ax_h.text(0.5, 0.62,
          "NAS-Guided FEM-Anchored PINNs for Transient Heat Transfer Simulation",
          ha="center", va="center", fontsize=16, fontweight="bold", color=WHITE,
          transform=ax_h.transAxes)
ax_h.text(0.5, 0.18,
          "Ömer Çetinkaya   ·   Supervisor: Prof. Turgay Celik   ·   University of Agder, 2026",
          ha="center", va="center", fontsize=10, color="#AACCEE",
          transform=ax_h.transAxes)

# ═══════════════════════════════════════════════════════════════════════════════
# ROW 1 — Benchmark Geometries
# ═══════════════════════════════════════════════════════════════════════════════
ax_r1t = fig.add_subplot(gs[1, :])
title_bar(ax_r1t,
    "Problem Setup & Domains  |  A356 aluminium water-quenching  ·  FEM ground-truth reference",
    C_BLUE)

# Col 0: problem text
ax_r1l = fig.add_subplot(gs[2, 0])
text_panel(ax_r1l, [
    "**A356 Aluminium Quenching**",
    "540°C → 20°C · 30 s",
    "Cooling gradients → distortion",
    "FEM ground-truth reference",
    "",
    "**Benchmark set**",
    "8 canonical benchmarks",
    "+ adaptive 2D study",
    "3 × 2D + 4 × 3D + Thermal Fin",
], bg=C_GREY_BG, fs=8.0, lh=1.28)

# Col 1: NAS 2D domains (Square, Circle, L-Shape, Flower)
ax_r1a = fig.add_subplot(gs[2, 1])
img_panel(ax_r1a, "fig1_naspinn_2d.png")

# Col 2: Canonical 2D (Rectangle, Circle, L-Shape)
ax_r1b = fig.add_subplot(gs[2, 2])
img_panel(ax_r1b, "fig2_thesis_2d.png")

# Col 3-4: 3D domains (wider)
ax_r1c = fig.add_subplot(gs[2, 3:5])
img_panel(ax_r1c, "fig3_thesis_3d.png")

# Col 5: Thermal Fin
ax_r1d = fig.add_subplot(gs[2, 5])
img_panel(ax_r1d, "fig4_thermalfin.png")

# ═══════════════════════════════════════════════════════════════════════════════
# ROW 2 — FEM | NAS-PINN | MSWP
# ═══════════════════════════════════════════════════════════════════════════════
ax_r2t = fig.add_subplot(gs[3, :])
title_bar(ax_r2t,
    "Methodology:  FEM Mesh & Solver  ·  Single-Window Model  ·  End-to-End Workflow  ·  MSWP Modes",
    C_TEAL)

method_gs = gs[4, :].subgridspec(
    2, 4,
    height_ratios=[0.065, 0.935],
    hspace=0.0,
    wspace=0.025,
)
ax_r2a = fig.add_subplot(method_gs[1, 0])
img_panel(ax_r2a, "FEM_Proses.png")

ax_r2b = fig.add_subplot(method_gs[1, 1])
img_panel(ax_r2b, "Single-Window FEM-Anchored NAS-PINN Framework.png")

ax_r2c = fig.add_subplot(method_gs[1, 2])
img_panel(ax_r2c, "fig6_naspinn_process.png")

ax_r2d = fig.add_subplot(method_gs[1, 3])
img_panel(ax_r2d, "fig_mswp_three_modes.png")

# ═══════════════════════════════════════════════════════════════════════════════
# ROW 3 — Key Results
# ═══════════════════════════════════════════════════════════════════════════════
ax_r3t = fig.add_subplot(gs[5, :])
title_bar(ax_r3t,
    "Key Results  |  FEM-call reduction vs. thermal prediction error across all studies",
    C_GREEN)

ax_r3a = fig.add_subplot(gs[6, :4])
key_results_panel(ax_r3a)

# Summary results table
ax_r3b = fig.add_subplot(gs[6, 4:])
ax_r3b.set_facecolor(C_GREY_BG)
ax_r3b.set_xticks([]); ax_r3b.set_yticks([])
for sp in ax_r3b.spines.values():
    sp.set_visible(True); sp.set_color(C_RULE); sp.set_linewidth(0.5)

rows = [
    ("Study",              "FEM saving", "Headline MAE"),
    ("2D adaptive-k transfer", "83–85%",  "< 2.5°C"),
    ("2D canonical fixed-k",  "65% robust", "Bayes k3 < 5°C"),
    ("3D canonical fixed-k",  "up to 80%", "Bayes k5 < 14.1°C"),
    ("Thermal Fin fixed-k",   "up to 80%", "Bayes k5 = 12.55°C"),
]
col_x = [0.04, 0.50, 0.75]
row_y = np.linspace(0.91, 0.56, len(rows))
for ri, row in enumerate(rows):
    bg = C_HEADER if ri == 0 else ("#EAF3FB" if ri % 2 == 1 else WHITE)
    tc = WHITE if ri == 0 else "#1A1A1A"
    fw = "bold" if ri == 0 else "normal"
    ax_r3b.add_patch(mpatches.FancyBboxPatch(
        (0.01, row_y[ri]-0.045), 0.98, 0.09,
        boxstyle="round,pad=0.01", fc=bg, ec="none",
        transform=ax_r3b.transAxes))
    for ci, cell in enumerate(row):
        ax_r3b.text(col_x[ci]+0.01, row_y[ri], cell,
                    ha="left", va="center", fontsize=8.6,
                    fontweight=fw, color=tc,
                    transform=ax_r3b.transAxes)

ax_r3b.axhline(0.50, color=C_RULE, lw=0.8, xmin=0.02, xmax=0.98)
bullets = [
    "● 2D adaptive-k: Square/Circle/L-Shape/Flower",
    "  83–85% saving, std < 0.10°C",
    "● 2D canonical: Rectangle/Circle/L-Shape",
    "  Bayesian/TPE: k=3 below 5°C",
    "● FEM anchoring essential: PINN-only best 59.20°C",
]
for i, b in enumerate(bullets):
    ax_r3b.text(0.04, 0.43 - i*0.076, b,
                ha="left", va="top", fontsize=8.1,
                color="#1A1A1A" if not b.startswith("●") else C_BLUE,
                fontweight="bold" if b.startswith("●") else "normal",
                transform=ax_r3b.transAxes)

# ═══════════════════════════════════════════════════════════════════════════════
# ROW 4 — Contributions & Impact
# ═══════════════════════════════════════════════════════════════════════════════
ax_r4t = fig.add_subplot(gs[7, :])
title_bar(ax_r4t,
    "Scientific Contribution & Literature Context",
    C_ORANGE)

ax_r4l = fig.add_subplot(gs[8, :3])
text_panel(ax_r4l, [
    "**Contributions & Impact**",
    "● NAS-guided PINN architecture optimisation",
    "● FEM-anchored MSWP error correction",
    "● Adaptive skip-factor scheduling (k=1–5)",
    "● Cross-geometry transfer across 2D and 3D domains",
    "● 10-seed reproducibility study",
    "● 65–85% reduction in FEM solver calls",
    "● Ready for h(T), material curves, and",
    "   industrial A356 subframe deployment",
], bg=C_GREY_BG, fs=8.5)

ax_r4r = fig.add_subplot(gs[8, 3:])
text_panel(ax_r4r, [
    "**Selected References**",
    "● Mortensen et al. (2026)",
    "   Industrial A356 subframe FEM quenching",
    "● Wang & Zhong (2024)",
    "   NAS-PINN architecture search framework",
    "● Rozza et al. (2008)",
    "   Reduced-basis benchmark foundation",
    "● Maday & Ronquist (2004)",
    "   Thermal Fin reduced-basis problem",
], bg="#FEF9EE", fs=8.5)

# ── Save ───────────────────────────────────────────────────────────────────────
fig.savefig(OUT / "visual_abstract.png", dpi=180, bbox_inches="tight",
            facecolor="white")
plt.close(fig)
print(f"Saved → {OUT / 'visual_abstract.png'}")
