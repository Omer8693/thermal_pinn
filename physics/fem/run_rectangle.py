"""
Rectangle FEM referans çözümü + görselleştirme.
Çalıştır: python3 thermal_pinn/physics/fem/run_rectangle.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri

from thermal_pinn.physics.fem.domains import build_rectangle_mesh
from thermal_pinn.physics.fem.base_solver import FEMSolver

# --- Parametreler ---
Lx, Ly   = 1.3, 0.6
T_INIT   = 540.0   # °C
T_W      = 20.0    # °C  (su)
K_COND   = 150.0   # W/mK  (A356)
RHO_CP   = 2.4e6   # J/m³K
H        = 5000.0  # W/m²K  (sabit)
DT       = 0.5     # s
T_SNAPSHOTS = [0.0, 5.0, 15.0, 30.0]

# --- Mesh ve solver ---
print("Mesh olusturuluyor...")
mesh = build_rectangle_mesh(Lx=Lx, Ly=Ly, resolution=40)
print(f"  {mesh.num_vertices()} dugum, {mesh.num_cells()} eleman")

solver = FEMSolver(
    mesh, T_init=T_INIT, T_w=T_W,
    k_cond=K_COND, rho_cp=RHO_CP,
    h_func=H, dt=DT,
)

# --- Hesaplama ---
snapshots = {}
coords = solver.get_coordinates()   # (N, 2)
x_all  = coords[:, 0]
y_all  = coords[:, 1]

rng = np.random.default_rng(0)

for t_snap in T_SNAPSHOTS:
    if t_snap == 0.0:
        T_arr = np.full(mesh.num_vertices(), T_INIT, dtype=float)
    else:
        solver.solve_until(t_snap)
        T_arr = solver.get_T_array()
    snapshots[t_snap] = T_arr.copy()
    print(f"  t={t_snap:5.1f}s  Tmin={T_arr.min():.1f}  Tmax={T_arr.max():.1f}  Tmean={T_arr.mean():.1f} C")

# --- Görsel ---
import matplotlib.colors as mcolors

fig, axes = plt.subplots(1, 4, figsize=(16, 4))

triang = mtri.Triangulation(x_all, y_all)
norm   = mcolors.Normalize(vmin=T_W, vmax=T_INIT)
cmap   = plt.cm.inferno
levels = np.linspace(T_W, T_INIT, 21)

for ax, t_snap in zip(axes, T_SNAPSHOTS):
    T_plot = snapshots[t_snap].copy()

    if T_plot.std() < 1e-3:
        color = cmap(norm(T_INIT))
        ax.add_patch(plt.Rectangle((0, 0), Lx, Ly, color=color))
        ax.set_xlim(0, Lx)
        ax.set_ylim(0, Ly)
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        tcf_last = sm
    else:
        tcf_last = ax.tricontourf(triang, T_plot, levels=levels,
                                   cmap=cmap, norm=norm, extend="both")

    cbar = fig.colorbar(tcf_last, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_ticks(np.linspace(T_W, T_INIT, 6))
    cbar.set_ticklabels([f"{v:.0f}" for v in np.linspace(T_W, T_INIT, 6)])
    cbar.set_label("T [°C]", fontsize=9)

    ax.set_title(f"t = {t_snap:.0f} s", fontsize=11)
    ax.set_xlabel("x [m]", fontsize=9)
    ax.set_ylabel("y [m]", fontsize=9)
    ax.set_aspect("equal")

fig.suptitle("Rectangle FEM — A356 quench (h=5000 W/m²K, constant)", fontsize=13)
plt.tight_layout()

out = Path("thermal_pinn/assets/fem/fem_rectangle_v2.png")
out.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out, dpi=150, facecolor=fig.get_facecolor())
print(f"\nGorsel kaydedildi: {out}")
