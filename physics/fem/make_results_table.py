"""
Tüm stratejiler için kapsamlı sonuç tablosu.
MAE, L2, Runtime, FEM tasarrufu — k=1..5, Adaptive-k, PINN-only.
Çalıştır: python3 thermal_pinn/physics/fem/make_results_table.py
"""

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

CKPT = Path("thermal_pinn/checkpoints")
OUT  = Path("thermal_pinn/assets/fem/results_table.png")
OUT.parent.mkdir(parents=True, exist_ok=True)

DOMAINS  = ["rectangle", "circle", "lshape"]
K_VALUES = [1, 2, 3, 4, 5]
BEST_K   = {"rectangle": 1, "circle": 4, "lshape": 5}

# ── Veri yükle ────────────────────────────────────────────────────────────────
def load(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.load(open(path))

rows = []   # (domain, label, strategy, k_used, mean_mae, mean_l2, total_s, n_win, fem_save)

for domain in DOMAINS:
    # Fixed k = 1..5
    for k in K_VALUES:
        f = CKPT / f"{domain}_bayesian_fem_hT_k{k}_dim2_metrics.json"
        r = load(f)
        if r is None:
            continue
        wins    = r["windows"]
        mean_l2 = float(np.mean([w["l2_rel"] for w in wins]))
        n_win   = r["n_windows"]
        fem_sav = (1 - n_win / 20) * 100
        rows.append((
            domain,
            f"Fixed k={k}",
            "fixed",
            k,
            r["mean_mae"],
            mean_l2,
            r.get("total_s", sum(w["runtime_s"] for w in wins)),
            n_win,
            fem_sav,
        ))

    # Adaptive-k
    f = CKPT / f"{domain}_bayesian_adaptive_fem_hT_dim2_metrics.json"
    r = load(f)
    if r:
        wins    = r["windows"]
        mean_l2 = float(np.mean([w["l2_rel"] for w in wins]))
        n_win   = r["n_windows"]
        fem_sav = r.get("fem_savings_pct", (1 - n_win / 20) * 100)
        k_sched = r.get("k_schedule", [])
        label   = f"Adaptive-k  [{','.join(str(k) for k in k_sched[:5])}…]"
        rows.append((
            domain,
            label,
            "adaptive",
            "—",
            r["mean_mae"],
            mean_l2,
            r.get("total_s", sum(w["runtime_s"] for w in wins)),
            n_win,
            fem_sav,
        ))

    # PINN-only
    f = CKPT / f"{domain}_bayesian_pinn_only_fem_hT_k1_dim2_metrics.json"
    r = load(f)
    if r:
        wins    = r["windows"]
        mean_l2 = float(np.mean([w["l2_rel"] for w in wins]))
        n_win   = r["n_windows"]
        rows.append((
            domain,
            "PINN-only  (no FEM anchor)",
            "pinn_only",
            "k=1",
            r["mean_mae"],
            mean_l2,
            r.get("total_s", sum(w["runtime_s"] for w in wins)),
            n_win,
            0.0,
        ))

# ── Tablo verisi ──────────────────────────────────────────────────────────────
col_headers = [
    "Domain", "Strategy", "k", "Mean MAE\n[°C]",
    "Mean L2\n[–]", "Runtime\n[s]", "Windows", "FEM saved\n[%]"
]

table_data = []
row_meta   = []   # (domain, strategy_type) for coloring

for (domain, label, stype, k, mae, l2, rt, nw, fsv) in rows:
    domain_disp = {"rectangle": "Rectangle", "circle": "Circle", "lshape": "L-shape"}[domain]
    table_data.append([
        domain_disp,
        label,
        str(k),
        f"{mae:.2f}",
        f"{l2:.4f}",
        f"{rt:.0f}",
        str(nw),
        f"{fsv:.0f}%",
    ])
    row_meta.append((domain, stype, k))

# ── Renk şeması ──────────────────────────────────────────────────────────────
def row_color(domain, stype, k):
    if stype == "pinn_only":
        return "#fde8e8"   # açık kırmızı
    if stype == "adaptive":
        return "#fff3cd"   # açık sarı
    # fixed k — best k'yı vurgula
    if isinstance(k, int) and k == BEST_K[domain]:
        return "#d4edda"   # açık yeşil (best)
    return "#ffffff"       # beyaz

# ── Matplotlib tablosu ───────────────────────────────────────────────────────
n_rows = len(table_data)
n_cols = len(col_headers)

fig_h = 0.38 * n_rows + 1.4
fig, ax = plt.subplots(figsize=(16, fig_h))
fig.patch.set_facecolor("white")
ax.axis("off")
ax.set_title(
    "NAS-PINN Bayesian 5×151 — FEM h(T) Training  |  All Strategies  |  2D Domains",
    fontsize=12, fontweight="bold", pad=14
)

# Tablo oluştur
tbl = ax.table(
    cellText=table_data,
    colLabels=col_headers,
    loc="center",
    cellLoc="center",
)
tbl.auto_set_font_size(False)
tbl.set_fontsize(9)
tbl.scale(1, 1.5)

# Header rengi
header_color = "#2c3e50"
for j in range(n_cols):
    cell = tbl[0, j]
    cell.set_facecolor(header_color)
    cell.set_text_props(color="white", fontweight="bold")

# Satır renkleri + domain sütunu birleştir görünümü (aynı domain için ilk sütun soluk)
prev_domain = None
for i, (domain, stype, k) in enumerate(row_meta):
    bg = row_color(domain, stype, k)
    for j in range(n_cols):
        cell = tbl[i + 1, j]
        cell.set_facecolor(bg)
        cell.set_edgecolor("#cccccc")

    # Domain sütununu sadece değiştiğinde göster
    if domain == prev_domain:
        tbl[i + 1, 0].get_text().set_text("")
        tbl[i + 1, 0].set_facecolor("#f5f5f5")
    else:
        tbl[i + 1, 0].get_text().set_fontweight("bold")
    prev_domain = domain

    # PINN-only satırını bold kırmızı yaz
    if stype == "pinn_only":
        for j in range(n_cols):
            tbl[i + 1, j].get_text().set_color("#cc0000")

    # Best k satırını bold yaz
    if stype == "fixed" and isinstance(k, int) and k == BEST_K[domain]:
        for j in range(n_cols):
            tbl[i + 1, j].get_text().set_fontweight("bold")

# Sütun genişlikleri
col_widths = [0.09, 0.26, 0.05, 0.09, 0.09, 0.08, 0.08, 0.09]
for j, w in enumerate(col_widths):
    for i in range(n_rows + 1):
        tbl[i, j].set_width(w)

# Legend
from matplotlib.patches import Patch
legend_elements = [
    Patch(facecolor="#d4edda", edgecolor="gray", label="Best fixed k (min MAE)"),
    Patch(facecolor="#fff3cd", edgecolor="gray", label="Adaptive-k"),
    Patch(facecolor="#fde8e8", edgecolor="gray", label="PINN-only (no FEM anchor)"),
    Patch(facecolor="white",   edgecolor="gray", label="Other fixed k"),
]
ax.legend(handles=legend_elements, loc="lower right",
          bbox_to_anchor=(0.98, 0.01), fontsize=8.5, framealpha=0.9)

plt.tight_layout()
plt.savefig(OUT, dpi=150, facecolor="white", bbox_inches="tight")
print(f"Tablo kaydedildi: {OUT}")

# Terminal özeti
print(f"\n{'Domain':<12} {'Strategy':<30} {'k':>3} {'MAE':>8} {'L2':>8} {'Runtime':>9} {'Win':>4} {'Saved':>6}")
print("-" * 80)
for (domain, label, stype, k, mae, l2, rt, nw, fsv) in rows:
    marker = " ★" if stype == "fixed" and isinstance(k, int) and k == BEST_K[domain] else ""
    print(f"{domain:<12} {label:<30} {str(k):>3} {mae:>7.2f}° {l2:>8.4f} {rt:>8.0f}s {nw:>4} {fsv:>5.0f}%{marker}")
