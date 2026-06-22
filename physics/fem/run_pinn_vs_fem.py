"""
PINN vs FEM karşılaştırması — Rectangle domain, sabit h=5000.
Çalıştır: python3 thermal_pinn/physics/fem/run_pinn_vs_fem.py
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

from thermal_pinn.network.pinn import ThermalPINN, make_pinn
from thermal_pinn.physics.fem.domains import build_rectangle_mesh
from thermal_pinn.physics.fem.base_solver import FEMSolver

# ── Sabitler ──────────────────────────────────────────────────────────────────
Lx, Ly   = 1.3, 0.6
T_INIT   = 540.0
T_WATER  = 20.0
DELTA_T  = T_INIT - T_WATER       # 520°C
DT_FEM   = 1.5                    # FEM zaman adımı [s]
K_SKIP   = 1                      # PINN pencere genişliği (k=1 → 1.5s)
ARCH     = "bayesian"
CKPT     = Path("thermal_pinn/checkpoints/rectangle_bayesian_k1_dim2.pt")

# Karşılaştırılacak zaman anları (FEM adım sonu)
T_COMPARE = [3.0, 6.0, 15.0, 30.0]   # her biri 1.5s'nin katı

# ── FEM çözümü (sabit h=5000) — her 1.5s adımda snapshot ────────────────────
print("FEM cozuluyor (sabit h=5000) — her pencere icin anchor kaydediliyor...")
mesh   = build_rectangle_mesh(Lx=Lx, Ly=Ly, resolution=40)
solver = FEMSolver(mesh, T_init=T_INIT, T_w=T_WATER,
                   k_cond=150.0, rho_cp=2.4e6, h_func=5000.0, dt=0.5)

coords_fem = solver.get_coordinates()   # (N_fem, 2)
x_fem, y_fem = coords_fem[:, 0], coords_fem[:, 1]

# Tüm 1.5s adımlarında snapshot al (0, 1.5, 3.0, ..., 30.0) — 21 adım
all_t = np.arange(0.0, 30.0 + 1e-9, DT_FEM)
fem_snapshots = {0.0: np.full(len(x_fem), T_INIT)}
for t in all_t[1:]:
    solver.solve_until(t)
    fem_snapshots[round(t, 6)] = solver.get_T_array().copy()

for t in T_COMPARE:
    T_arr = fem_snapshots[round(t, 6)]
    print(f"  FEM t={t:.1f}s  Tmin={T_arr.min():.1f}  Tmean={T_arr.mean():.1f}°C")

# ── PINN yükleme ──────────────────────────────────────────────────────────────
print(f"\nPINN yukleniyor: {CKPT}")
ckpt   = torch.load(CKPT, map_location="cpu", weights_only=False)
model  = make_pinn(dim=2, arch=ckpt.get("arch", ARCH))
model.load_state_dict(ckpt["model_state"])
model  = model.cpu()
model.eval()
print(f"  {model}  mean_mae={ckpt['mean_mae']:.3f}°C")

# ── PINN değerlendirme — pencere pencere ──────────────────────────────────────
# Normalised FEM koordinatları
x_norm = x_fem / Lx
y_norm = y_fem / Ly
coords_norm_np = np.stack([x_norm, y_norm], axis=1).astype(np.float32)
coords_t = torch.tensor(coords_norm_np)
tau_one  = torch.ones(len(x_fem), 1)

def theta_from_T(T_arr):
    return ((T_arr - T_WATER) / DELTA_T).astype(np.float32)

pinn_snapshots = {}

print("\nPINN pencere degerlendirmesi (her pencere FEM anchor aliyor — k=1):")
for t_start, t_end in zip(all_t[:-1], all_t[1:]):
    t_s = round(t_start, 6)
    t_e = round(t_end, 6)
    # FEM IC'i al (doğru anchor)
    T_ic_arr = fem_snapshots[t_s].astype(np.float32)
    theta_ic = torch.tensor(theta_from_T(T_ic_arr).reshape(-1, 1))
    with torch.no_grad():
        theta_pred = model(coords_t, tau_one, theta_ic).numpy().flatten()
    T_pinn = T_WATER + DELTA_T * theta_pred

    if t_e in [round(t, 6) for t in T_COMPARE]:
        pinn_snapshots[t_e] = T_pinn.copy()
        T_fem_e = fem_snapshots[t_e]
        mae  = float(np.mean(np.abs(T_pinn - T_fem_e)))
        l2   = float(np.linalg.norm(T_pinn - T_fem_e) /
                     (np.linalg.norm(T_fem_e - T_WATER) + 1e-10))
        print(f"  t={t_e:.1f}s  Tmin={T_pinn.min():.1f}  Tmean={T_pinn.mean():.1f}°C  "
              f"MAE={mae:.2f}°C  L2rel={l2:.4f}")

# ── Görsel ────────────────────────────────────────────────────────────────────
n_snaps = len(T_COMPARE)
fig, axes = plt.subplots(3, n_snaps, figsize=(4 * n_snaps, 10))
fig.suptitle("PINN vs FEM — Rectangle (h=5000 W/m²K, constant)", fontsize=13)

triang  = mtri.Triangulation(x_fem, y_fem)
norm_T  = mcolors.Normalize(vmin=T_WATER, vmax=T_INIT)
cmap_T  = plt.cm.inferno
levels  = np.linspace(T_WATER, T_INIT, 21)

row_labels = ["FEM", "PINN", "Error |FEM−PINN|"]
err_max    = max(
    np.abs(pinn_snapshots[t] - fem_snapshots[t]).max()
    for t in T_COMPARE
)
norm_err   = mcolors.Normalize(vmin=0, vmax=max(err_max, 1.0))
cmap_err   = plt.cm.hot_r

for col, t in enumerate(T_COMPARE):
    T_fem  = fem_snapshots[t]
    T_pinn = pinn_snapshots[t]
    T_err  = np.abs(T_pinn - T_fem)
    mae    = float(T_err.mean())
    l2     = float(np.linalg.norm(T_pinn - T_fem) /
                   (np.linalg.norm(T_fem - T_WATER) + 1e-10))

    for row, (data, nm, err_mode) in enumerate([
        (T_fem,  f"FEM  t={t:.0f}s", False),
        (T_pinn, f"PINN t={t:.0f}s", False),
        (T_err,  f"|Err|  MAE={mae:.2f}°C  L2={l2:.3f}", True),
    ]):
        ax = axes[row][col]
        if err_mode:
            tcf = ax.tricontourf(triang, data, levels=20,
                                  cmap=cmap_err, norm=norm_err)
            cbar = fig.colorbar(tcf, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label("[°C]", fontsize=8)
        else:
            tcf = ax.tricontourf(triang, data, levels=levels,
                                  cmap=cmap_T, norm=norm_T, extend="both")
            cbar = fig.colorbar(tcf, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_ticks(np.linspace(T_WATER, T_INIT, 5))
            cbar.set_ticklabels([f"{v:.0f}" for v in np.linspace(T_WATER, T_INIT, 5)])
            cbar.set_label("T [°C]", fontsize=8)

        ax.set_title(nm, fontsize=9)
        ax.set_xlabel("x [m]", fontsize=8)
        ax.set_ylabel("y [m]", fontsize=8)
        ax.set_aspect("equal")

plt.tight_layout()
out = Path("thermal_pinn/assets/fem/pinn_vs_fem_rectangle.png")
out.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out, dpi=150)
print(f"\nGorsel kaydedildi: {out}")
