"""
experiments/tm_adaptive_k_rectangle_fenics/live_fem_reference.py
===================================================================
LiveFEMReference — wraps the REAL FEniCS solver (thermal_pinn.physics.fem
.base_solver.FEMSolver on a mshr-generated mesh) behind the exact same
domain interface that thermal_pinn.training.trainer expects
(.T(x, y, t), .sample_interior(n, rng), .sample_boundary(n, rng), plus the
.alpha / .h / .Lx / .Ly attributes), so train_window / evaluate_window /
the adaptive-k controller loop do not need to change at all.

Why this exists
----------------
The rest of the codebase (thermal_pinn.physics.fem_reference.
make_reference_domain) uses a PRE-COMPUTED, interpolated snapshot file
(fem_hT_rectangle.npz, h=700 film-boiling constant). That was almost
certainly a later substitute for environments without a working FEniCS
install. FEMSolver's own defaults (k=150 W/mK, rho_cp=2.4e6, h=5000 W/m2K,
internal dt=0.5s) match the thesis's official parameter table
(results_2d.tex) exactly, so this class uses those defaults to reproduce
the setup that actually matches the reported numbers - just solved live
instead of replayed from a cache.

Design notes
------------
- FEMSolver only solves FORWARD in time (implicit Euler, irreversible
  state). All windows in this experiment are visited in increasing time
  order, so this is not a limitation in practice - but T(x, y, t) will
  raise if asked to go backwards past the current solver time.
- Each time a new time point is reached, the nodal solution is pulled out
  of dolfin and wrapped in the SAME LinearNDInterpolator / NearestNDInterpolator
  pattern already used by FEMReference (physics/fem/fem_reference.py), so
  arbitrary (x, y) query points (not just mesh nodes) can be evaluated
  quickly and in a vectorised way, rather than calling the slow
  dolfin.Function point-evaluation once per point. Already-reached times
  are cached (dict keyed by rounded t) so repeated IC/BC queries at the
  same t_start/t_end within one window do not re-solve anything.
"""

from __future__ import annotations

import numpy as np
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator

from thermal_pinn.physics.fem.base_solver import FEMSolver
from thermal_pinn.physics.fem.domains import (
    build_circle_mesh, build_lshape_mesh, build_rectangle_mesh,
)

# Matches the project's _DOMAIN_PARAMS_2D (physics/fem/fem_reference.py
# convention) so live-FEniCS geometry/coords line up with the rest of the
# repo's rectangle/circle/lshape figures.
GEOMETRY_PARAMS = {
    "rectangle": {"Lx": 1.3, "Ly": 0.6, "x_min": 0.0, "y_min": 0.0, "R": None},
    "circle": {"Lx": 0.6, "Ly": 0.6, "x_min": -0.3, "y_min": -0.3, "R": 0.3},
    "lshape": {"Lx": 2.0, "Ly": 2.0, "x_min": 0.0, "y_min": 0.0, "R": None},
}


class LiveFEMReference:
    # Matches reports/thesis_uia/chapters/results_2d.tex Table "Physical and
    # training parameters for the 2D benchmark simulations" AND
    # FEMSolver's own class defaults.
    K_COND_DEFAULT = 150.0
    RHO_CP_DEFAULT = 2.4e6
    H_DEFAULT = 5000.0
    T_INIT_DEFAULT = 540.0
    T_W_DEFAULT = 20.0
    DT_INTERNAL_DEFAULT = 0.5  # matches theory.tex's internal FD/FEM step

    def __init__(
        self,
        geometry: str = "rectangle",
        resolution: int = 30,
        dt: float = DT_INTERNAL_DEFAULT,
        k_cond: float = K_COND_DEFAULT,
        rho_cp: float = RHO_CP_DEFAULT,
        h: float = H_DEFAULT,
        T_init: float = T_INIT_DEFAULT,
        T_w: float = T_W_DEFAULT,
    ):
        if geometry not in GEOMETRY_PARAMS:
            raise ValueError(f"geometry must be one of {list(GEOMETRY_PARAMS)}, got {geometry!r}")
        params = GEOMETRY_PARAMS[geometry]
        self.geometry = geometry
        self.Lx = params["Lx"]
        self.Ly = params["Ly"]
        self.x_min = params["x_min"]
        self.y_min = params["y_min"]
        self.R = params["R"]
        self.k_cond = k_cond
        self.rho_cp = rho_cp
        self.alpha = k_cond / rho_cp
        self.h = h
        self.T_init = T_init
        self.T_w = T_w

        if geometry == "rectangle":
            mesh = build_rectangle_mesh(self.Lx, self.Ly, resolution=resolution)
        elif geometry == "circle":
            mesh = build_circle_mesh(self.R, resolution=resolution)
        else:  # lshape
            mesh = build_lshape_mesh(self.Lx, resolution=resolution)

        self.solver = FEMSolver(
            mesh, T_init=T_init, T_w=T_w, k_cond=k_cond, rho_cp=rho_cp,
            h_func=h, dt=dt,
        )
        self._cache: dict[float, tuple] = {}
        self._store_snapshot(0.0)

    # ------------------------------------------------------------------
    # Internal: solve-forward + interpolator cache
    # ------------------------------------------------------------------
    def _store_snapshot(self, t: float) -> None:
        vals = self.solver.get_T_array().astype(np.float64)
        coords = self.solver.get_coordinates().astype(np.float64)
        lin = LinearNDInterpolator(coords, vals)
        near = NearestNDInterpolator(coords, vals)
        self._cache[round(t, 6)] = (lin, near)

    def _interpolators_at(self, t: float) -> tuple:
        key = round(t, 6)
        if key in self._cache:
            return self._cache[key]
        if t < self.solver.t - 1e-9:
            raise ValueError(
                f"LiveFEMReference is forward-only: requested t={t} but "
                f"solver is already at t={self.solver.t}"
            )
        self.solver.solve_until(t)
        self._store_snapshot(self.solver.t)
        return self._cache[round(self.solver.t, 6)]

    # ------------------------------------------------------------------
    # domain.T(x, y, t) interface (trainer.py / feature_logging_run.py)
    # ------------------------------------------------------------------
    def T(self, x: np.ndarray, y: np.ndarray, t: float) -> np.ndarray:
        lin, near = self._interpolators_at(t)
        pts = np.stack(
            [np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)], axis=1
        )
        out = lin(pts)
        mask = np.isnan(out)
        if mask.any():
            out[mask] = near(pts[mask])
        return out

    # ------------------------------------------------------------------
    # Sampling — identical convention to physics/fem/fem_reference.py's
    # FEMReference (same geometry branches), so window collocation
    # statistics are directly comparable across the cached and live FEM
    # references. lshape boundary sampling reuses the rectangle's 4-edge
    # sampler (matches FEMReference's existing simplification: it does not
    # carve out the notch's boundary either) - not fixed here, kept
    # consistent with the rest of the repo.
    # ------------------------------------------------------------------
    def sample_interior(self, n: int, rng=None) -> tuple:
        if rng is None:
            rng = np.random.default_rng()
        if self.geometry == "circle":
            pts = []
            while len(pts) < n:
                batch = rng.uniform(-self.R, self.R, (n * 4, 2))
                inside = batch[:, 0] ** 2 + batch[:, 1] ** 2 < self.R ** 2 * 0.95
                pts.extend(batch[inside].tolist())
            arr = np.array(pts[:n], dtype=np.float32)
            return arr[:, 0], arr[:, 1]
        elif self.geometry == "lshape":
            pts = []
            L = self.Lx
            while len(pts) < n:
                batch = rng.uniform(0, L, (n * 4, 2))
                inside = ~((batch[:, 0] > L / 2) & (batch[:, 1] > L / 2))
                pts.extend(batch[inside].tolist())
            arr = np.array(pts[:n], dtype=np.float32)
            return arr[:, 0], arr[:, 1]
        else:  # rectangle
            x = rng.uniform(self.x_min, self.x_min + self.Lx, n).astype(np.float32)
            y = rng.uniform(self.y_min, self.y_min + self.Ly, n).astype(np.float32)
            return x, y

    def sample_boundary(self, n: int, rng=None) -> tuple:
        if rng is None:
            rng = np.random.default_rng()
        if self.geometry == "circle":
            theta = rng.uniform(0, 2 * np.pi, n).astype(np.float32)
            bx = (self.R * np.cos(theta)).astype(np.float32)
            by = (self.R * np.sin(theta)).astype(np.float32)
            nx, ny = np.cos(theta).astype(np.float32), np.sin(theta).astype(np.float32)
            return bx, by, nx, ny
        n_per_edge = n // 4
        x0, y0 = self.x_min, self.y_min
        Lx, Ly = self.Lx, self.Ly
        parts = [
            (np.full(n_per_edge, x0), rng.uniform(y0, y0 + Ly, n_per_edge),
             -np.ones(n_per_edge), np.zeros(n_per_edge)),
            (np.full(n_per_edge, x0 + Lx), rng.uniform(y0, y0 + Ly, n_per_edge),
             np.ones(n_per_edge), np.zeros(n_per_edge)),
            (rng.uniform(x0, x0 + Lx, n_per_edge), np.full(n_per_edge, y0),
             np.zeros(n_per_edge), -np.ones(n_per_edge)),
            (rng.uniform(x0, x0 + Lx, n_per_edge), np.full(n_per_edge, y0 + Ly),
             np.zeros(n_per_edge), np.ones(n_per_edge)),
        ]
        bx = np.concatenate([p[0] for p in parts]).astype(np.float32)
        by = np.concatenate([p[1] for p in parts]).astype(np.float32)
        nx = np.concatenate([p[2] for p in parts]).astype(np.float32)
        ny = np.concatenate([p[3] for p in parts]).astype(np.float32)
        return bx, by, nx, ny
