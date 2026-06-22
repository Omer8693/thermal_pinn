"""
FEM veri üretici — h(T) boiling curve ile tüm domainler için snapshot.
Çıktı: thermal_pinn/data/fem_hT_{domain}.npz

Her .npz içeriği:
  coords  : (N, 2)  — FEM mesh DOF koordinatları [m]
  T_snaps : (21, N) — t=0,1.5,...,30s sıcaklık alanları [°C]
  t_snaps : (21,)   — zaman vektörü [s]

Çalıştır: python3 thermal_pinn/physics/fem/generate_fem_data.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
from thermal_pinn.physics.fem.base_solver import FEMSolver
from thermal_pinn.physics.fem.domains import build_rectangle_mesh
from thermal_pinn.physics.fem.boiling_curve import h_boiling

OUT_DIR = Path("thermal_pinn/data")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Ortak parametreler ────────────────────────────────────────────────────────
T_INIT  = 540.0
T_WATER = 20.0
K_COND  = 150.0
RHO_CP  = 2.4e6
DT_FEM  = 0.5           # ince iç adım (kararlılık için)
T_SNAPS = np.arange(0.0, 30.0 + 1e-9, 1.5)   # 21 snapshot

def run_domain(name, mesh, resolution_label):
    print(f"\n{'='*55}")
    print(f"Domain: {name}  ({mesh.num_vertices()} dugum, {mesh.num_cells()} eleman)")
    print(f"{'='*55}")

    solver = FEMSolver(
        mesh, T_init=T_INIT, T_w=T_WATER,
        k_cond=K_COND, rho_cp=RHO_CP,
        h_func=h_boiling, dt=DT_FEM,
    )
    coords = solver.get_coordinates()   # (N, 2)
    N      = len(coords)
    T_all  = np.zeros((len(T_SNAPS), N), dtype=np.float32)

    T_all[0] = T_INIT   # t=0

    for i, t in enumerate(T_SNAPS[1:], start=1):
        solver.solve_until(t)
        T_all[i] = solver.get_T_array().astype(np.float32)
        print(f"  t={t:5.1f}s  Tmin={T_all[i].min():.1f}  Tmax={T_all[i].max():.1f}  "
              f"Tmean={T_all[i].mean():.1f}°C")

    out = OUT_DIR / f"fem_hT_{name}.npz"
    np.savez_compressed(out,
                        coords=coords.astype(np.float32),
                        T_snaps=T_all,
                        t_snaps=T_SNAPS.astype(np.float32))
    print(f"  --> Kaydedildi: {out}  ({out.stat().st_size/1024:.1f} KB)")

# ── Rectangle ─────────────────────────────────────────────────────────────────
mesh_rect = build_rectangle_mesh(Lx=1.3, Ly=0.6, resolution=40)
run_domain("rectangle", mesh_rect, "res40")

# ── Circle ────────────────────────────────────────────────────────────────────
from thermal_pinn.physics.fem.domains import build_circle_mesh
mesh_circle = build_circle_mesh(R=0.3, resolution=40)
run_domain("circle", mesh_circle, "res40")

# ── LShape ────────────────────────────────────────────────────────────────────
from thermal_pinn.physics.fem.domains import build_lshape_mesh
mesh_lshape = build_lshape_mesh(L=2.0, resolution=30)
run_domain("lshape", mesh_lshape, "res30")

print("\nTUM DOMAINLER TAMAMLANDI.")
print("Cikti dosyalari:")
for f in sorted(OUT_DIR.glob("fem_hT_*.npz")):
    print(f"  {f}  ({f.stat().st_size/1024:.1f} KB)")
