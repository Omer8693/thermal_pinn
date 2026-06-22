"""
3 domain — FEM h(T) vs PINN best-k karşılaştırması.
Pre-generated .npz dosyalarından yükler (dolfin gerekmez).
Çalıştır: python3 thermal_pinn/physics/fem/run_all_domains_compare.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.tri as mtri

from thermal_pinn.network.pinn import make_pinn

T_INIT, T_WATER, DELTA_T = 540.0, 20.0, 520.0
DT_FEM = 1.5
DATA_DIR = Path("thermal_pinn/data")

DOMAINS = {
    "rectangle": {
        "npz":   DATA_DIR / "fem_hT_rectangle.npz",
        "ckpt":  "thermal_pinn/checkpoints/rectangle_bayesian_fem_hT_k1_dim2.pt",
        "k_skip": 1,
        "Lx": 1.3, "Ly": 0.6,
        "interior_fn": lambda x, y, eps=0.02: (
            (x > eps) & (x < 1.3 - eps) & (y > eps) & (y < 0.6 - eps)
        ),
    },
    "circle": {
        "npz":   DATA_DIR / "fem_hT_circle.npz",
        "ckpt":  "thermal_pinn/checkpoints/circle_bayesian_fem_hT_k1_dim2.pt",
        "k_skip": 1,
        "Lx": 0.6, "Ly": 0.6,
        "interior_fn": lambda x, y, R=0.3, eps=0.02: (x**2 + y**2 < (R - eps)**2),
    },
    "lshape": {
        "npz":   DATA_DIR / "fem_hT_lshape.npz",
        "ckpt":  "thermal_pinn/checkpoints/lshape_bayesian_fem_hT_k2_dim2.pt",
        "k_skip": 2,
        "Lx": 2.0, "Ly": 2.0,
        "interior_fn": lambda x, y, eps=0.04: (
            (x > eps) & (y > eps) &
            ~((x > 1.0 - eps) & (y > 1.0 - eps)) &
            (x < 2.0 - eps) & (y < 2.0 - eps)
        ),
    },
}

T_SNAP = 15.0
all_t  = np.arange(0.0, 30.0 + 1e-9, DT_FEM)

# ── Her domain için FEM yükle + PINN değerlendir ─────────────────────────────
results = {}

for dname, cfg in DOMAINS.items():
    print(f"\n{'='*50}\n{dname.upper()}")

    # .npz'den yükle
    data   = np.load(cfg["npz"])
    coords = data["coords"]          # (N, 2)
    T_snaps_arr = data["T_snaps"]    # (n_t, N)
    t_snaps_arr = data["t_snaps"]    # (n_t,)

    x_all, y_all = coords[:, 0], coords[:, 1]
    fem_snaps = {round(float(t), 6): T_snaps_arr[i].astype(np.float32)
                 for i, t in enumerate(t_snaps_arr)}
    print(f"  FEM t=15s: Tmin={fem_snaps[15.0].min():.1f}  Tmean={fem_snaps[15.0].mean():.1f}°C")

    # Interior mask
    mask   = cfg["interior_fn"](x_all, y_all)
    x_int, y_int = x_all[mask], y_all[mask]

    # PINN yükle
    ckpt  = torch.load(cfg["ckpt"], map_location="cpu", weights_only=False)
    model = make_pinn(dim=2, arch=ckpt.get("arch", "bayesian"))
    model.load_state_dict(ckpt["model_state"])
    model = model.cpu().eval()

    Lx, Ly = cfg["Lx"], cfg["Ly"]
    # Trainer _normalise_coords: lo=0, hi=Lx
    x_norm_int = (x_int / Lx).astype(np.float32)
    y_norm_int = (y_int / Ly).astype(np.float32)
    coords_t = torch.tensor(np.stack([x_norm_int, y_norm_int], axis=1))
    tau_one  = torch.ones(len(x_int), 1)

    k = cfg["k_skip"]
    T_pinn_snap = None

    for t_start, t_end in zip(all_t[:-1:k], all_t[k::k]):
        t_s = round(float(t_start), 6)
        t_e = round(float(t_end),   6)
        T_ic      = fem_snaps[t_s][mask].astype(np.float32)
        theta_ic  = torch.tensor(((T_ic - T_WATER) / DELTA_T).reshape(-1, 1))
        with torch.no_grad():
            theta_pred = model(coords_t, tau_one, theta_ic).numpy().flatten()
        T_pinn = T_WATER + DELTA_T * theta_pred
        if abs(t_e - T_SNAP) < 1e-6:
            T_pinn_snap = T_pinn.copy()

    T_fem_snap = fem_snaps[round(T_SNAP, 6)][mask]
    mae = np.mean(np.abs(T_pinn_snap - T_fem_snap))
    l2  = np.linalg.norm(T_pinn_snap - T_fem_snap) / (np.linalg.norm(T_fem_snap - T_WATER) + 1e-10)
    print(f"  PINN k={k}  MAE={mae:.2f}°C  L2={l2:.4f}")

    results[dname] = {
        "x": x_int, "y": y_int,
        "T_fem":  T_fem_snap,
        "T_pinn": T_pinn_snap,
        "mae": mae, "l2": l2, "k": k,
    }

# ── Görsel: 3 domain × 3 satır ───────────────────────────────────────────────
fig, axes = plt.subplots(3, 3, figsize=(15, 11))
fig.patch.set_facecolor("white")
fig.suptitle(f"FEM h(T) vs PINN — t={T_SNAP:.0f}s  (A356 water quench)", fontsize=13, y=0.98)

norm_T   = mcolors.Normalize(vmin=T_WATER, vmax=T_INIT)
cmap_T   = plt.cm.inferno
levels_T = np.linspace(T_WATER, T_INIT, 21)
cmap_err = plt.cm.YlOrRd

col_labels = {
    "rectangle": "Rectangle  (1.3×0.6 m)",
    "circle":    "Circle  (R=0.3 m)",
    "lshape":    "L-shape  (2×2 m)",
}

for col, (dname, res) in enumerate(results.items()):
    triang = mtri.Triangulation(res["x"], res["y"])

    # L-shape: Delaunay notch'u doldurur — centroid bazlı maskeleme ile kaldır
    if dname == "lshape":
        tri_pts = triang.triangles          # (n_tri, 3)
        cx = res["x"][tri_pts].mean(axis=1)
        cy = res["y"][tri_pts].mean(axis=1)
        bad = (cx > 1.0) & (cy > 1.0)      # [L/2, L]×[L/2, L] notch
        triang.set_mask(bad)

    k = res["k"]

    # Per-domain hata skalası — her subplot kendi aralığında
    err_max    = max(float(np.percentile(np.abs(res["T_pinn"] - res["T_fem"]), 99)), 1.0)
    norm_err   = mcolors.Normalize(vmin=0, vmax=err_max)
    levels_err = np.linspace(0, err_max, 21)

    for row, (data_arr, is_err) in enumerate([
        (res["T_fem"],                           False),
        (res["T_pinn"],                          False),
        (np.abs(res["T_pinn"] - res["T_fem"]),   True),
    ]):
        ax = axes[row][col]
        ax.set_facecolor("white")

        if is_err:
            tcf  = ax.tricontourf(triang, data_arr, levels=levels_err,
                                  cmap=cmap_err, norm=norm_err, extend="max")
            cbar = fig.colorbar(tcf, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label("[°C]", fontsize=8)
            cbar.set_ticks(np.linspace(0, err_max, 5))
            cbar.set_ticklabels([f"{v:.0f}" for v in np.linspace(0, err_max, 5)])
            ax.set_title(f"MAE = {res['mae']:.2f}°C   L2 = {res['l2']:.3f}",
                         fontsize=9, color="#cc0000", fontweight="bold")
        else:
            tcf  = ax.tricontourf(triang, data_arr, levels=levels_T, cmap=cmap_T,
                                  norm=norm_T, extend="both")
            cbar = fig.colorbar(tcf, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_ticks(np.linspace(T_WATER, T_INIT, 5))
            cbar.set_ticklabels([f"{v:.0f}" for v in np.linspace(T_WATER, T_INIT, 5)])
            cbar.set_label("T [°C]", fontsize=8)
            if row == 0:
                ax.set_title(f"{col_labels[dname]}\nFEM h(T)", fontsize=9, fontweight="bold")
            else:
                ax.set_title(f"PINN  k={k}", fontsize=9)

        ax.set_xlabel("x [m]", fontsize=8)
        ax.set_ylabel("y [m]", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.set_aspect("equal")

# Satır etiketleri (sol kenarda)
for row, lbl in enumerate(["FEM h(T)", "PINN (best k)", "|Error|  [°C]"]):
    axes[row][0].annotate(lbl, xy=(-0.22, 0.5), xycoords="axes fraction",
                          fontsize=10, fontweight="bold", rotation=90,
                          va="center", ha="center", color="#333333")

plt.tight_layout(rect=[0.04, 0, 1, 0.97])
out = Path("thermal_pinn/assets/fem/all_domains_pinn_vs_fem_hT.png")
out.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out, dpi=150, facecolor="white", bbox_inches="tight")
print(f"\nGorsel: {out}")
