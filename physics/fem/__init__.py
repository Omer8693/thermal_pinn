"""FEniCS-based FEM reference solvers for thermal_pinn domains."""
from .base_solver import FEMSolver
from .domains import build_rectangle_mesh, build_circle_mesh, build_lshape_mesh

__all__ = [
    "FEMSolver",
    "build_rectangle_mesh",
    "build_circle_mesh",
    "build_lshape_mesh",
]
