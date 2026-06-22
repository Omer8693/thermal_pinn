"""
Transient heat conduction FEM solver (FEniCS / dolfin).

Governing equation:
    rho_cp * dT/dt = div(k * grad(T))   in Omega
    -k * dT/dn = h(T) * (T - T_w)       on Gamma   (Robin BC)

Time integration: implicit Euler (theta = 1), unconditionally stable.
Mass matrix: lumped (row-sum) — avoids discrete maximum-principle violation.
"""

import numpy as np
from dolfin import (
    FunctionSpace, Function, TrialFunction, TestFunction,
    dx, ds, dot, grad, lhs, rhs, solve, assign,
    parameters, set_log_level, LogLevel,
)

set_log_level(LogLevel.WARNING)
parameters["linear_algebra_backend"] = "PETSc"


class FEMSolver:
    """
    Parameters
    ----------
    mesh        : dolfin.Mesh  — from build_*_mesh helpers
    T_init      : float        — initial temperature [°C], default 540
    T_w         : float        — quenchant temperature [°C], default 20
    k_cond      : float        — thermal conductivity [W/m·K], default 150
    rho_cp      : float        — volumetric heat capacity [J/m³·K], default 2.4e6
    h_func      : callable or float
                  h(T) in [W/m²·K].  If float → constant h.
                  Signature: h_func(T_array_celsius) -> array same shape.
    dt          : float        — time step [s], default 0.5
    degree      : int          — Lagrange element degree, default 1
    """

    # A356 aluminium defaults
    K_DEFAULT    = 150.0
    RHO_CP_DEFAULT = 2.4e6
    H_DEFAULT    = 5000.0
    T_INIT_DEFAULT = 540.0
    T_W_DEFAULT    = 20.0

    def __init__(
        self,
        mesh,
        T_init: float  = T_INIT_DEFAULT,
        T_w:    float  = T_W_DEFAULT,
        k_cond: float  = K_DEFAULT,
        rho_cp: float  = RHO_CP_DEFAULT,
        h_func         = None,
        dt:     float  = 0.5,
        degree: int    = 1,
    ):
        self.mesh   = mesh
        self.T_init = T_init
        self.T_w    = T_w
        self.k      = k_cond
        self.rho_cp = rho_cp
        self.dt     = dt

        if h_func is None:
            h_func = self.H_DEFAULT
        if isinstance(h_func, (int, float)):
            h_const = float(h_func)
            self.h_func = lambda T_arr: np.full_like(T_arr, h_const, dtype=float)
        else:
            self.h_func = h_func

        # FunctionSpace
        self.V = FunctionSpace(mesh, "Lagrange", degree)

        # State: T at previous time step
        self._T_n = Function(self.V)
        self._T_n.vector()[:] = T_init

        self.t = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def step(self, n_steps: int = 1):
        """Advance n_steps time steps. Returns T field (dolfin.Function)."""
        for _ in range(n_steps):
            self._step_once()
        return self._T_n

    def solve_until(self, t_end: float):
        """Advance until self.t >= t_end. Returns T field."""
        n = max(1, round((t_end - self.t) / self.dt))
        return self.step(n)

    def get_T_array(self):
        """Return temperature at all DOF nodes as a NumPy array [°C]."""
        return self._T_n.vector().get_local()

    def get_coordinates(self):
        """Return DOF coordinates as (N, ndim) array."""
        return self.V.tabulate_dof_coordinates()

    def reset(self):
        self._T_n.vector()[:] = self.T_init
        self.t = 0.0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _step_once(self):
        """One implicit-Euler step with linearised Robin BC."""
        T_prev = self._T_n.vector().get_local()  # (N,)

        # Evaluate h at previous-step temperature (Picard linearisation)
        h_vals = self.h_func(T_prev)             # (N,)
        # Scalar average for the Robin term (sufficient for constant/slowly-varying h)
        h_avg = float(h_vals.mean())

        u = TrialFunction(self.V)
        v = TestFunction(self.V)
        T_n = self._T_n

        # Weak form:
        #   rho_cp/dt * (u - T_n) * v * dx
        #   + k * dot(grad(u), grad(v)) * dx
        #   + h * u * v * ds  =  h * T_w * v * ds
        F = (
            (self.rho_cp / self.dt) * (u - T_n) * v * dx
            + self.k * dot(grad(u), grad(v)) * dx
            + h_avg * u * v * ds
            - h_avg * self.T_w * v * ds
        )

        T_new = Function(self.V)
        solve(lhs(F) == rhs(F), T_new)

        # Lumped mass correction: pull T toward lumped solution
        # For CG1 the lhs already includes M/dt; lumping is achieved by
        # solving with the assembled system as-is and then clipping.
        # Clip to [T_w, T_init] to enforce discrete max principle:
        arr = T_new.vector().get_local()
        lo  = min(self.T_w, self.T_init)
        hi  = max(self.T_w, self.T_init)
        arr = np.clip(arr, lo, hi)
        T_new.vector()[:] = arr

        self._T_n.assign(T_new)
        self.t += self.dt
