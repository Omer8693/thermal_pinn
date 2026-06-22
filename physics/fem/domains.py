"""
Mesh builders for thermal_pinn 2-D domains using FEniCS + mshr.

Available builders
------------------
build_rectangle_mesh(Lx, Ly, resolution)
    Rectangular plate.  thermal_pinn default: Lx=1.3, Ly=0.6

build_circle_mesh(R, resolution)
    Solid disc.

build_annulus_mesh(R_inner, R_outer, resolution)
    Hollow cylinder cross-section.

build_lshape_mesh(L, resolution)
    L-shaped domain:  [0,L]x[0,L]  minus  [L/2,L]x[L/2,L]

All return a dolfin.Mesh ready for use with FEMSolver.
"""

from dolfin import Mesh, Point
from mshr import Rectangle, Circle, generate_mesh


def build_rectangle_mesh(Lx: float = 1.3, Ly: float = 0.6, resolution: int = 30) -> Mesh:
    domain = Rectangle(Point(0.0, 0.0), Point(Lx, Ly))
    return generate_mesh(domain, resolution)


def build_circle_mesh(R: float = 0.3, resolution: int = 40) -> Mesh:
    domain = Circle(Point(0.0, 0.0), R)
    return generate_mesh(domain, resolution)


def build_annulus_mesh(
    R_inner: float = 0.1,
    R_outer: float = 0.3,
    resolution: int = 40,
) -> Mesh:
    outer = Circle(Point(0.0, 0.0), R_outer)
    inner = Circle(Point(0.0, 0.0), R_inner)
    return generate_mesh(outer - inner, resolution)


def build_lshape_mesh(L: float = 2.0, resolution: int = 30) -> Mesh:
    full  = Rectangle(Point(0.0, 0.0), Point(L, L))
    notch = Rectangle(Point(L / 2, L / 2), Point(L, L))
    return generate_mesh(full - notch, resolution)
