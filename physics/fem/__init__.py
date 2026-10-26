"""
FEniCS-based FEM reference solvers for thermal_pinn domains.

FEMSolver and mesh builders require dolfin (FEniCS). They are NOT imported
at package level to avoid breaking environments without FEniCS installed.
FEMReference (npz-based interpolation) works without dolfin and is always safe.

Usage with dolfin available:
    from thermal_pinn.physics.fem.base_solver import FEMSolver
    from thermal_pinn.physics.fem.domains import build_rectangle_mesh

Usage without dolfin (default runtime):
    from thermal_pinn.physics.fem.fem_reference import FEMReference
"""
