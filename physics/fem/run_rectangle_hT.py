"""
Rectangle FEM — h(T) nonlinear boiling curve karşılaştırması.
Çalıştır: python3 thermal_pinn/physics/fem/run_rectangle_hT.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.tri as mtri

from thermal_pinn.physics.fem.domains import build_rectangle_mesh
from thermal_pinn.physics.fem.base_solver import FEMSolver
from thermal_pinn.physics.fem.boiling_curve import h_boiling

# --- Parametreler ---
Lx, Ly = 1.3, 0.6
T_INIT  = 540.0
T_W     = 20.0
K_COND  = 150.0
RHO_CP  = 2.4e6
DT      = 0.5
T_SNAPSHOTS = [0.0, 5.0, 15.0, 30.0]

print("Mesh olusturuluyor...")
mesh = build_rectangle_mesh(Lx=Lx, Ly=Ly, resolution=40)
print(f"  {mesh.num_vertices()} dugum, {mesh.num_cells()} eleman\n")

# --- İki solver: sabit h vs h(T) ---
solvers = {
    "Constant h=5000": FEMSolver(mesh, T_init=T_INIT, T_w=T_W,
                                  k_cond=K_COND, rho_cp=RHO_CP,
                                  h_func=5000.0, dt=DT),
    "h(T) boiling":   FEMSolver(mesh, T_init=T_INIT, T_w=T_W,
                                  k_cond=K_COND, rho_cp=RHO_CP,
                                  h_func=h_boiling, dt=DT),
}

snapshots = {label: {} for label in solvers}
coords = list(solvers.values())[0].get_coordinates()
x_all, y_all = coords[:, 0], coords[:, 1]

for label, solver in solvers.items():
    print(f"Cozuluyor: {label}")
    for t_snap in T_SNAPSHOTS:
        if t_snap == 0.0:
            T_arr = np.full(mesh.num_vertices(), T_INIT)
        else:
            solver.solve_until(t_snap)
            T_arr = solver.get_T_array()
        snapshots[label][t_snap] = T_arr.copy()
        print(f"  t={t_snap:5.1f}s  Tmin={T_arr.min():.1f}  Tmax={T_arr.max():.1f}  Tmean={T_arr.mean():.1f} C")
    print()

# --- Görsel: 2 satır × 4 sütun ---
fig, axes = plt.subplots(2, 4, figsize=(16, 8))
fig.suptitle("Rectangle FEM — Constant h vs h(T) boiling curve", fontsize=13)

triang = mtri.Triangulation(x_all, y_all)
norm   = mcolors.Normalize(vmin=T_W, vmax=T_INIT)
cmap   = plt.cm.inferno
levels = np.linspace(T_W, T_INIT, 21)
row_labels = list(solvers.keys())

for row, label in enumerate(row_labels):
    for col, t_snap in enumerate(T_SNAPSHOTS):
        ax = axes[row][col]
        T_plot = snapshots[label][t_snap].copy()

        if T_plot.std() < 1e-3:
            color = cmap(norm(T_INIT))
            ax.add_patch(plt.Rectangle((0, 0), Lx, Ly, color=color))
            ax.set_xlim(0, Lx); ax.set_ylim(0, Ly)
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
            sm.set_array([])
            tcf = sm
        else:
            tcf = ax.tricontourf(triang, T_plot, levels=levels,
                                  cmap=cmap, norm=norm, extend="both")

        cbar = fig.colorbar(tcf, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_ticks(np.linspace(T_W, T_INIT, 5))
        cbar.set_ticklabels([f"{v:.0f}" for v in np.linspace(T_W, T_INIT, 5)])
        cbar.set_label("T [°C]", fontsize=8)

        if row == 0:
            ax.set_title(f"t = {t_snap:.0f} s", fontsize=10)
        if col == 0:
            ax.set_ylabel(f"{label}\ny [m]", fontsize=8)
        else:
            ax.set_ylabel("y [m]", fontsize=8)
        ax.set_xlabel("x [m]", fontsize=8)
        ax.set_aspect("equal")

plt.tight_layout()
out = Path("thermal_pinn/assets/fem/fem_rectangle_hT_compare.png")
out.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(out, dpi=150)
print(f"Gorsel kaydedildi: {out}")

# --- Sayısal karşılaştırma ---
print("\n=== Tmean karşılaştırması ===")
print(f"{'t [s]':>8}  {'Const h [°C]':>14}  {'h(T) [°C]':>12}  {'Fark [°C]':>10}")
for t_snap in T_SNAPSHOTS[1:]:
    T_const = snapshots["Constant h=5000"][t_snap].mean()
    T_hT    = snapshots["h(T) boiling"][t_snap].mean()
    print(f"{t_snap:8.1f}  {T_const:14.2f}  {T_hT:12.2f}  {T_hT - T_const:+10.2f}")
