"""
PINN vs FEM h(T) karşılaştırması — Rectangle domain.
Çalıştır: python3 thermal_pinn/physics/fem/run_pinn_vs_fem_hT.py
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
from thermal_pinn.physics.fem.domains import build_rectangle_mesh
from thermal_pinn.physics.fem.base_solver import FEMSolver
from thermal_pinn.physics.fem.boiling_curve import h_boiling
from thermal_pinn.physics.fem.fem_reference import FEMReference

# ── Sabitler ──────────────────────────────────────────────────────────────────
Lx, Ly  = 1.3, 0.6
T_INIT  = 540.0
T_WATER = 20.0
DELTA_T = T_INIT - T_WATER
DT_FEM  = 1.5
T_COMPARE = [3.0, 6.0, 15.0, 30.0]   # k=2 pencere ucları: 3,6,9,...30

CKPT_K1 = Path("thermal_pinn/checkpoints/rectangle_bayesian_fem_hT_k1_dim2.pt")
CKPT_K2 = Path("thermal_pinn/checkpoints/rectangle_bayesian_fem_hT_k2_dim2.pt")

# ── FEM mesh + FEMReference ───────────────────────────────────────────────────
print("FEM mesh ve referans yukleniyor...")
mesh   = build_rectangle_mesh(Lx=Lx, Ly=Ly, resolution=40)
solver = FEMSolver(mesh, T_init=T_INIT, T_w=T_WATER,
                   k_cond=150.0, rho_cp=2.4e6, h_func=h_boiling, dt=0.5)
coords_fem = solver.get_coordinates()
x_fem, y_fem = coords_fem[:, 0], coords_fem[:, 1]

# Tüm 1.5s adımlarda FEM snapshot
all_t = np.arange(0.0, 30.0 + 1e-9, DT_FEM)
fem_snaps = {0.0: np.full(len(x_fem), T_INIT, dtype=np.float32)}
print("FEM h(T) cozuluyor (21 snapshot)...")
for t in all_t[1:]:
    solver.solve_until(t)
    fem_snaps[round(t, 6)] = solver.get_T_array().astype(np.float32)
print(f"  t=30s  Tmin={fem_snaps[30.0].min():.1f}  Tmean={fem_snaps[30.0].mean():.1f}°C")

# FEMReference interpolator (IC için)
ref = FEMReference("thermal_pinn/data/fem_hT_rectangle.npz", Lx=Lx, Ly=Ly)

# ── PINN yükleme ──────────────────────────────────────────────────────────────
def load_model(ckpt_path):
    ckpt  = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    model = make_pinn(dim=2, arch=ckpt.get("arch", "bayesian"))
    model.load_state_dict(ckpt["model_state"])
    return model.cpu().eval()

print("\nPINN modeller yukleniyor...")
model_k1 = load_model(CKPT_K1)
model_k2 = load_model(CKPT_K2)
print("  k=1 ve k=2 yuklen di")

# ── PINN değerlendirme ────────────────────────────────────────────────────────
# Interior maske — sınırdan eps mesafede olan düğümleri çıkar
eps = 0.02
interior_mask = (
    (x_fem > eps) & (x_fem < Lx - eps) &
    (y_fem > eps) & (y_fem < Ly - eps)
)
x_int, y_int = x_fem[interior_mask], y_fem[interior_mask]
print(f"Interior dugum sayisi: {interior_mask.sum()} / {len(x_fem)}")

x_norm_int = (x_int / Lx).astype(np.float32)
y_norm_int = (y_int / Ly).astype(np.float32)
coords_t = torch.tensor(np.stack([x_norm_int, y_norm_int], axis=1))
tau_one  = torch.ones(len(x_int), 1)

def eval_pinn(model, k_skip):
    pinn_snaps = {}
    t_compare_set = {round(t, 6) for t in T_COMPARE}
    print(f"\n  k={k_skip} PINN degerlendirmesi:")
    for t_start, t_end in zip(all_t[:-1:k_skip], all_t[k_skip::k_skip]):
        t_s = round(t_start, 6)
        t_e = round(t_end, 6)
        T_ic_full = fem_snaps.get(t_s, None)
        if T_ic_full is None:
            continue
        T_ic = T_ic_full[interior_mask]
        theta_ic = torch.tensor(((T_ic - T_WATER) / DELTA_T).reshape(-1, 1))
        with torch.no_grad():
            theta_pred = model(coords_t, tau_one, theta_ic).numpy().flatten()
        T_pinn = T_WATER + DELTA_T * theta_pred
        if t_e in t_compare_set:
            pinn_snaps[t_e] = T_pinn
            T_fem_e = fem_snaps[t_e][interior_mask]
            mae = np.mean(np.abs(T_pinn - T_fem_e))
            l2  = np.linalg.norm(T_pinn - T_fem_e) / (np.linalg.norm(T_fem_e - T_WATER) + 1e-10)
            print(f"    t={t_e:.1f}s  MAE={mae:.2f}°C  L2={l2:.4f}")
    return pinn_snaps

pinn_k1 = eval_pinn(model_k1, k_skip=1)
pinn_k2 = eval_pinn(model_k2, k_skip=2)

# ── Görsel: 4 satır × 4 sütun ────────────────────────────────────────────────
fig, axes = plt.subplots(4, 4, figsize=(16, 14))
fig.suptitle("PINN vs FEM h(T) — Rectangle (A356 water quench)", fontsize=13)

triang  = mtri.Triangulation(x_int, y_int)
norm_T  = mcolors.Normalize(vmin=T_WATER, vmax=T_INIT)
cmap_T  = plt.cm.inferno
levels  = np.linspace(T_WATER, T_INIT, 21)

err_max = max(
    max(np.abs(pinn_k1.get(round(t,6), fem_snaps[round(t,6)][interior_mask]) - fem_snaps[round(t,6)][interior_mask]).max(),
        np.abs(pinn_k2.get(round(t,6), fem_snaps[round(t,6)][interior_mask]) - fem_snaps[round(t,6)][interior_mask]).max())
    for t in T_COMPARE
)
norm_err = mcolors.Normalize(vmin=0, vmax=max(err_max, 1.0))
cmap_err = plt.cm.hot_r

row_labels = ["FEM h(T)", "PINN k=1", "|Err| k=1", "PINN k=2"]

for col, t in enumerate(T_COMPARE):
    t_key = round(t, 6)
    T_fem  = fem_snaps[t_key][interior_mask]
    T_pk1  = pinn_k1.get(t_key, T_fem)
    T_pk2  = pinn_k2.get(t_key, T_fem)
    err_k1 = np.abs(T_pk1 - T_fem)
    err_k2 = np.abs(T_pk2 - T_fem)
    mae_k1 = err_k1.mean()
    mae_k2 = err_k2.mean()

    rows = [
        (T_fem,  f"FEM  t={t:.0f}s",             False),
        (T_pk1,  f"k=1  MAE={mae_k1:.2f}°C",     False),
        (err_k1, f"|Err k=1|  L2={np.linalg.norm(T_pk1-T_fem)/(np.linalg.norm(T_fem-T_WATER)+1e-10):.3f}", True),
        (T_pk2,  f"k=2  MAE={mae_k2:.2f}°C",     False),
    ]

    for row, (data, title, is_err) in enumerate(rows):
        ax = axes[row][col]
        if is_err:
            tcf  = ax.tricontourf(triang, data, levels=20, cmap=cmap_err, norm=norm_err)
            cbar = fig.colorbar(tcf, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label("[°C]", fontsize=7)
        else:
            tcf  = ax.tricontourf(triang, data, levels=levels, cmap=cmap_T, norm=norm_T, extend="both")
            cbar = fig.colorbar(tcf, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_ticks(np.linspace(T_WATER, T_INIT, 5))
            cbar.set_ticklabels([f"{v:.0f}" for v in np.linspace(T_WATER, T_INIT, 5)])
            cbar.set_label("T [°C]", fontsize=7)

        ax.set_title(title, fontsize=8)
        ax.set_xlabel("x [m]", fontsize=7)
        ax.set_ylabel("y [m]", fontsize=7)
        ax.tick_params(labelsize=7)
        ax.set_aspect("equal")

# Satır etiketleri
for row, lbl in enumerate(row_labels):
    axes[row][0].set_ylabel(f"{lbl}\ny [m]", fontsize=8)

plt.tight_layout()
out = Path("thermal_pinn/assets/fem/pinn_vs_fem_hT_rectangle.png")
out.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out, dpi=150)
print(f"\nGorsel: {out}")
