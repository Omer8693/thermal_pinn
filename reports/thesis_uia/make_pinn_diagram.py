"""
NAS-PINN framework diagram — faithful to user's draw.io layout,
with academic improvements:
  - Fourier Feature box removed (clarified as direct-input note)
  - Loss descriptions shortened to one crisp line each
  - Subtle colour coding per component type
  - Backpropagation arc rendered explicitly
  - Curly-brace NAS→PINN connector kept

Run from repo root:
    python thermal_pinn/reports/thesis_uia/make_pinn_diagram.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.lines import Line2D
import numpy as np
from pathlib import Path

# ── Canvas ────────────────────────────────────────────────────────────────────
W, H = 24, 12
fig, ax = plt.subplots(figsize=(W, H))
ax.set_xlim(0, W); ax.set_ylim(0, H)
ax.axis("off")
fig.patch.set_facecolor("white")

# ── Colour palette (subtle, academic) ────────────────────────────────────────
C_FEM   = "#EBF4FA"   # very light blue  — FEM / spatial
C_FEM_E = "#5B9BD5"   # border blue
C_IC    = "#F0EBF8"   # very light purple — IC field
C_IC_E  = "#8064A2"   # border purple
C_NAS   = "#EBF4FA"   # light blue       — NAS block
C_NAS_E = "#2E75B6"   # border dark blue
C_PINN  = "#F2F2F2"   # light grey       — PINN network
C_PINN_E= "#404040"   # border dark grey
C_OUT   = "#FDF5E0"   # very light amber  — IC-consistent output
C_OUT_E = "#C09000"
C_LOSS  = "#F9F9F9"   # near-white        — loss boxes
C_LOSS_E= "#7F7F7F"   # grey border
C_TOT   = "#FCF0E6"   # light orange      — total loss
C_TOT_E = "#C0392B"

# ── Helpers ───────────────────────────────────────────────────────────────────
def box(x, y, w, h, fc=C_FEM, ec=C_FEM_E, lw=1.8, r="round,pad=0.06", zord=3):
    p = FancyBboxPatch((x, y), w, h, boxstyle=r, fc=fc, ec=ec, lw=lw, zorder=zord)
    ax.add_patch(p); return p

def txt(x, y, s, sz=9.5, bold=False, col="#1a1a1a", ha="center", va="center",
        italic=False, zord=6):
    ax.text(x, y, s, ha=ha, va=va, fontsize=sz, color=col, zorder=zord,
            fontweight="bold" if bold else "normal",
            fontstyle="italic" if italic else "normal")

def arr(x1, y1, x2, y2, col="#5B9BD5", lw=1.6, hw=12):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=col,
                                lw=lw, mutation_scale=hw), zorder=7)

def arr_curve(x1, y1, x2, y2, rad=0.25, col="#5B9BD5", lw=1.6, hw=12):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=col, lw=lw,
                                mutation_scale=hw,
                                connectionstyle=f"arc3,rad={rad}"), zorder=7)

# ── Title ─────────────────────────────────────────────────────────────────────
txt(W/2, H - 0.30,
    "NAS-PINN: Architecture Search and Window-Based Training",
    sz=15, bold=True, col="#1a1a1a")

# ══════════════════════════════════════════════════════════════════════════════
# COL 1 — FEM Anchor  +  Spatial Input
# ══════════════════════════════════════════════════════════════════════════════
BW1, BH1 = 2.8, 2.0   # standard box size for Col 1

# FEM Anchor
FA_X, FA_Y = 0.4, 7.5
box(FA_X, FA_Y, BW1, BH1, fc=C_FEM, ec=C_FEM_E)
txt(FA_X+BW1/2, FA_Y+BH1*0.70, r"FEM Anchor $(t_k)$", sz=10.5, bold=True, col="#1a4e79")
txt(FA_X+BW1/2, FA_Y+BH1*0.28, r"$u(\mathbf{x},\,t_k)$", sz=10)

# "FEM solver called at t_k" chip above
ax.text(FA_X+BW1/2, FA_Y+BH1+0.45,
        r"FEM solver called at $t_k$",
        ha="center", va="center", fontsize=8.5, color=C_FEM_E,
        bbox=dict(boxstyle="round,pad=0.22", fc=C_FEM, ec=C_FEM_E, lw=1.1), zorder=6)
arr(FA_X+BW1/2, FA_Y+BH1+0.20, FA_X+BW1/2, FA_Y+BH1, col=C_FEM_E, lw=1.4)

# Spatial Input
SI_X, SI_Y = 0.4, 1.8
box(SI_X, SI_Y, BW1, BH1, fc=C_FEM, ec=C_FEM_E)
txt(SI_X+BW1/2, SI_Y+BH1*0.70, "Spatial Input",          sz=10.5, bold=True, col="#1a4e79")
txt(SI_X+BW1/2, SI_Y+BH1*0.28, r"$x,\;y,\;(z),\;\tau$", sz=10)
txt(SI_X+BW1/2, SI_Y-0.32,
    r"$\tau = (t - t_k)/\Delta t_k \;\in [0,1]$",
    sz=7.8, col="#555", italic=True)

# ══════════════════════════════════════════════════════════════════════════════
# COL 2 — Initial Field  (Fourier box removed; note on arrow instead)
# ══════════════════════════════════════════════════════════════════════════════
IF_X, IF_Y, IF_W, IF_H = 3.6, 7.0, 3.2, 2.5
box(IF_X, IF_Y, IF_W, IF_H, fc=C_IC, ec=C_IC_E)
txt(IF_X+IF_W/2, IF_Y+IF_H*0.82, r"Initial Field $(u_{ic})$",
    sz=10.5, bold=True, col="#4a235a")
txt(IF_X+IF_W/2, IF_Y+IF_H*0.56,
    r"$u_{ic}(\mathbf{x}) = u(\mathbf{x},\,t_k)$", sz=9.5)
txt(IF_X+IF_W/2, IF_Y+IF_H*0.28,
    r"$\hat{u} = u_{ic} + \tau\,N_\phi(\mathbf{x},\tau,u_{ic})$", sz=9)

# FEM Anchor → Initial Field
arr(FA_X+BW1, FA_Y+BH1/2, IF_X, IF_Y+IF_H/2, col=C_IC_E, lw=1.6)

# ══════════════════════════════════════════════════════════════════════════════
# CONCAT node  ⊕
# ══════════════════════════════════════════════════════════════════════════════
CX, CY = 7.6, 5.5
c = mpatches.Circle((CX, CY), 0.36, fc="#FFF3E0", ec="#E65100", lw=2.0, zorder=8)
ax.add_patch(c)
txt(CX, CY, r"$\oplus$", sz=13, bold=True, col="#E65100", zord=9)

# Initial Field → concat  (right edge of IF → concat top)
arr_curve(IF_X+IF_W, IF_Y+IF_H*0.40,
          CX, CY+0.36, rad=-0.18, col=C_IC_E, lw=1.6)
txt(IF_X+IF_W+0.45, IF_Y+IF_H*0.50+0.25,
    r"$u_{ic}$  $[\mathrm{N}{\times}1]$", sz=8.5, col=C_IC_E, ha="left")

# Spatial Input → concat  (with "Direct input" note, no Fourier box)
arr_curve(SI_X+BW1, SI_Y+BH1/2,
          CX, CY-0.36, rad=0.20, col=C_FEM_E, lw=1.6)
txt(4.8, 3.5,
    r"coords  $[\mathrm{N}{\times}4/5]$" "\n(direct input, no Fourier)",
    sz=8, col=C_FEM_E, italic=False)

# ══════════════════════════════════════════════════════════════════════════════
# COL 3 — NAS block  +  PINN Network
# ══════════════════════════════════════════════════════════════════════════════
PX, PY, PW, PH = 8.2, 1.2, 4.8, 7.2    # PINN box
NX, NY, NW, NH = 8.2, 9.2, 4.8, 1.9    # NAS block

# ── NAS block ─────────────────────────────────────────────────────────────────
box(NX, NY, NW, NH, fc=C_NAS, ec=C_NAS_E, lw=2.0)
txt(NX+NW/2, NY+NH-0.27,
    "Neural Architecture Search (NAS)",
    sz=10, bold=True, col=C_NAS_E)

SUB_W = NW/3
SUB_H = NH - 0.65
SUB_Y = NY + 0.12

for i, (lbl, col_s) in enumerate([
    ("Bayesian/TPE\n5×151 ReLU", "#2E75B6"),
    ("NSGA-II\n3×153 tanh",      "#7030A0"),
    ("NSGA-III\n3×75 tanh",      "#375623"),
]):
    bx = NX + i*SUB_W + 0.10
    sw = SUB_W - 0.20
    box(bx, SUB_Y, sw, SUB_H,
        fc="white", ec=col_s, lw=1.4, r="round,pad=0.04")
    txt(bx+sw/2, SUB_Y+SUB_H/2, lbl, sz=8.5, col=col_s, bold=True)

# Curly-brace connector: 3 boxes → single arrow to PINN
# Drawn as three short lines converging to a midpoint, then one arrow down
mid_x = NX + NW/2
brk_y = NY - 0.10    # bottom of NAS box with small margin

# Horizontal lines from each sub-box bottom to mid_x
for i in range(3):
    sx = NX + (i + 0.5)*SUB_W
    ax.plot([sx, sx], [SUB_Y, brk_y], color=C_NAS_E, lw=1.3, zorder=5)
ax.plot([NX+0.5*SUB_W, NX+2.5*SUB_W], [brk_y, brk_y],
        color=C_NAS_E, lw=1.3, zorder=5)
ax.plot([mid_x, mid_x], [brk_y, PY+PH+0.10],
        color=C_NAS_E, lw=1.3, zorder=5)

# Arrow into PINN
arr(mid_x, PY+PH+0.10, mid_x, PY+PH, col=C_NAS_E, lw=1.6)
txt(mid_x+1.35, (PY+PH + brk_y)/2,
    r"Selected architecture for $N_\phi$",
    sz=8.5, col=C_NAS_E, italic=True, ha="left")

# ── PINN Network ──────────────────────────────────────────────────────────────
box(PX, PY, PW, PH, fc=C_PINN, ec=C_PINN_E, lw=2.0)
txt(PX+PW/2, PY+PH-0.42,
    r"PINN Network $N_\phi$", sz=12, bold=True, col=C_PINN_E)

# Neurons: 5 rows × 3 cols
n_rows = [PY+1.0, PY+2.2, PY+3.4, PY+4.6, PY+5.8]
n_cols = [PX+0.9, PX+2.4, PX+3.9]
for ry in n_rows:
    for cx2 in n_cols:
        ax.add_patch(mpatches.Ellipse((cx2, ry), 0.55, 0.32,
                                      fc="#d9d9d9", ec=C_PINN_E,
                                      lw=0.9, zorder=5))
    if ry < n_rows[-1]:
        txt(PX+PW/2, ry+0.60, "·  ·  ·", sz=13, col="#777")

txt(PX+PW/2, PY+0.28,
    r"$L$ Layers,  $N$ neurons,  activation $\phi$",
    sz=8.5, col="#555")

# Curly braces on PINN sides (visual, drawn with bezier)
def _curly(ax, x, y_bot, y_top, opening="left", col="#888", lw=1.2):
    """Draw a curly brace using bezier patches."""
    mid_y = (y_bot + y_top) / 2
    sign  = -1 if opening == "left" else 1
    bump  = 0.22 * sign
    pts_top = np.array([
        [x, y_top],
        [x + bump, y_top],
        [x + bump, mid_y + (y_top-y_bot)*0.12],
        [x, mid_y],
    ])
    pts_bot = np.array([
        [x, mid_y],
        [x + bump, mid_y - (y_top-y_bot)*0.12],
        [x + bump, y_bot],
        [x, y_bot],
    ])
    from matplotlib.path import Path
    import matplotlib.patches as mpatch
    verts_top = [(pts_top[0,0], pts_top[0,1]),
                 (pts_top[1,0], pts_top[1,1]),
                 (pts_top[2,0], pts_top[2,1]),
                 (pts_top[3,0], pts_top[3,1])]
    codes_top = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4]
    verts_bot = [(pts_bot[0,0], pts_bot[0,1]),
                 (pts_bot[1,0], pts_bot[1,1]),
                 (pts_bot[2,0], pts_bot[2,1]),
                 (pts_bot[3,0], pts_bot[3,1])]
    codes_bot = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4]
    from matplotlib.path import Path
    p1 = mpatch.PathPatch(Path(verts_top, codes_top),
                          fc="none", ec=col, lw=lw, zorder=8)
    p2 = mpatch.PathPatch(Path(verts_bot, codes_bot),
                          fc="none", ec=col, lw=lw, zorder=8)
    ax.add_patch(p1); ax.add_patch(p2)

_curly(ax, PX - 0.05, PY+0.05, PY+PH-0.05, opening="left",  col="#888", lw=1.4)
_curly(ax, PX+PW+0.05, PY+0.05, PY+PH-0.05, opening="right", col="#888", lw=1.4)

# Concat → PINN
arr(CX+0.36, CY, PX, PY+PH*0.68, col="#E65100", lw=1.8, hw=13)
txt(7.95, PY+PH*0.68+0.28,
    r"$[u_{ic},\;x,\;y,\;(z),\;\tau]$",
    sz=9, col="#E65100", bold=True)

# ══════════════════════════════════════════════════════════════════════════════
# COL 4 — IC-Consistent Output
# ══════════════════════════════════════════════════════════════════════════════
OX, OY, OW, OH = 13.4, 5.1, 3.6, 3.2
box(OX, OY, OW, OH, fc=C_OUT, ec=C_OUT_E, lw=1.8)
txt(OX+OW/2, OY+OH*0.85, "IC-Consistent Output",
    sz=10.5, bold=True, col="#7d5000")
txt(OX+OW/2, OY+OH*0.62,
    r"$\hat{u}(\mathbf{x},t) = u_{ic} + \tau \cdot N_\phi(\mathbf{x},t)$",
    sz=9.2)
txt(OX+OW/2, OY+OH*0.42,
    r"$\hat{u}(\mathbf{x},0) = u_{ic}$ by construction",
    sz=8.8, italic=True, col="#555")
txt(OX+OW/2, OY+OH*0.20,
    r"$\hat{u}$ is consistent with IC",
    sz=8.8, italic=True, col="#7d5000")

# PINN → IC-Output
arr(PX+PW, PY+PH*0.68, OX, OY+OH/2, col=C_NAS_E, lw=1.6)

# ══════════════════════════════════════════════════════════════════════════════
# COL 5 — Loss terms  (1 bold symbol + 1 short description line)
# ══════════════════════════════════════════════════════════════════════════════
LX, LW, LH = 17.4, 4.1, 1.30
LH_GAP      = 0.18   # vertical gap between loss boxes

loss_defs = [
    (r"$\mathcal{L}_{pde}$",
     r"PDE residual $\mathcal{R}(u,\mathbf{x},t)$",
     C_LOSS, "#2E75B6", 9.20),
    (r"$\mathcal{L}_{bc}$",
     r"Boundary condition error $u_{\partial\Omega}$",
     C_LOSS, "#375623", 7.68),
    (r"$\mathcal{L}_{ic}$",
     r"Initial condition error at $t = t_k$",
     C_LOSS, "#7030A0", 6.16),
    (r"$\mathcal{L}_{end}$",
     r"Endpoint error vs. FEM at $t = t_{k+1}$",
     C_LOSS, "#C0392B", 4.64),
]

O_cx = OX + OW   # right edge of IC-Output box
O_cy = OY + OH/2 # mid-height of IC-Output

for sym, desc, fc, ec, ly in loss_defs:
    box(LX, ly, LW, LH, fc=fc, ec=ec, lw=1.5)
    txt(LX+LW/2, ly+LH*0.72, sym,  sz=13, bold=True, col=ec)
    txt(LX+LW/2, ly+LH*0.26, desc, sz=8.5, col="#333")
    # IC-Output → each loss (converging arrows)
    arr(O_cx, O_cy, LX, ly+LH/2, col="#888", lw=1.3, hw=10)

# Total Weighted Loss
LY_TOT = 2.50; LH_TOT = 1.55
box(LX, LY_TOT, LW, LH_TOT, fc=C_TOT, ec=C_TOT_E, lw=2.0)
txt(LX+LW/2, LY_TOT+LH_TOT*0.72,
    r"$\mathcal{L} = \sum_i w_i\,\mathcal{L}_i$",
    sz=12, bold=True, col="#922B21")
txt(LX+LW/2, LY_TOT+LH_TOT*0.30,
    "Total Weighted Loss (L2-norm)", sz=8.8, col="#555")

# Loss boxes → Total (downward arrows along left edge)
for *_, ly in loss_defs:
    arr(LX+LW*0.40, ly,
        LX+LW*0.40, LY_TOT+LH_TOT,
        col=C_TOT_E, lw=1.2, hw=9)

# ══════════════════════════════════════════════════════════════════════════════
# Backpropagation — explicit curved arc from Total Loss to PINN bottom
# ══════════════════════════════════════════════════════════════════════════════
ax.annotate("",
    xy  =(PX+PW/2, PY),
    xytext=(LX+LW/2, LY_TOT),
    arrowprops=dict(
        arrowstyle="-|>",
        connectionstyle="arc3,rad=-0.32",
        color="#9E9E9E", lw=1.8, mutation_scale=14),
    zorder=7)
txt((PX+PW/2 + LX+LW/2)/2, PY - 0.45,
    "Backpropagation", sz=9.5, col="#9E9E9E", italic=True)

# ══════════════════════════════════════════════════════════════════════════════
# LEGEND
# ══════════════════════════════════════════════════════════════════════════════
legend_items = [
    (C_FEM,  C_FEM_E, "FEM / Spatial input"),
    (C_IC,   C_IC_E,  r"IC field $u_{ic}$"),
    (C_NAS,  C_NAS_E, "NAS / PINN network"),
    (C_OUT,  C_OUT_E, r"IC-consistent output $\hat{u}$"),
    (C_LOSS, "#888",  "Loss terms (e.g., MSE)"),
]
item_w = W / len(legend_items)
for i, (fc, ec, lbl) in enumerate(legend_items):
    lx2 = 0.5 + i*item_w
    ax.add_patch(FancyBboxPatch((lx2, 0.08), 0.28, 0.22,
                                boxstyle="round,pad=0.03",
                                fc=fc, ec=ec, lw=1.2, zorder=5))
    txt(lx2+1.05, 0.19, lbl, sz=8.5, col="#333", ha="center")

# ── Save ──────────────────────────────────────────────────────────────────────
plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
out = Path(__file__).parent / "Figures" / "pinn_framework_diagram.png"
out.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out, dpi=180, bbox_inches="tight",
            facecolor="white", edgecolor="none")
print(f"Saved → {out}")
