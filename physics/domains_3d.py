"""
thermal_pinn/physics/domains_3d.py
===================================
Self-contained 3D transient heat conduction domains for water quenching of
A356 aluminium alloy.  All four geometries from the Level 8 MCO-PINN benchmark
are implemented here without any cross-folder imports.

Domain list
-----------
    Rectangular3D  — 3D rectangular prism, separable product solution
    Cylinder3D     — 3D cylinder, Bessel (radial) × plane-wall (axial)
    StackedCubes3D — two square prisms stacked axially (Shen et al., 2023)
    LShape3D       — L-shaped cross-section × depth, explicit FD reference

Physical problem
----------------
    ∂T/∂t = α · ∇²T         in Ω,  t ∈ [0, 30 s]
    k · ∂T/∂n + h(T − T_w) = 0    on ∂Ω  (Robin / Newton cooling BC)
    T(x, 0) = T_init = 540 °C     (uniform initial condition after solution)

The four geometries are chosen to span separable (analytic) to irregular
(numerical) domains, following the benchmark methodology in Shen et al. (2023).
Rectangular and Stacked correspond to the main casting cross-section in
Mortensen et al. (2026). Cylinder represents suspension knuckles. L-Shape
captures T-junction structural nodes common in automotive subframes.

References
----------
    [1] Wang, Y., & Zhong, L. (2023). NAS-PINN: Neural Architecture
        Search-Guided PINN for Solving PDEs. arXiv:2305.10127.
    [2] Mortensen, D., Noorsumar, G., Fjær, H.G., Babaei, R., & Drønen, P.E.
        (2026). Mitigating distortions in cast automotive subframes: A finite
        element simulation approach. Int J Adv Manuf Technol.
        DOI: 10.1007/s00170-026-17515-w
    [3] Shen, L. et al. (2023). MCO-PINN: Multi-continuity operator
        physics-informed neural network for complex geometry heat transfer.
    [4] Carslaw, H.S., & Jaeger, J.C. (1959). Conduction of Heat in Solids,
        2nd ed. Oxford University Press.  [eigenvalue derivations]
    [5] Incropera, F.P. et al. (2007). Fundamentals of Heat and Mass Transfer,
        6th ed. Wiley.  [Robin BC treatment]
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq
from scipy.special import j0, j1
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import distance_transform_edt

# ──────────────────────────────────────────────────────────────────────────────
# Physical constants  —  A356 aluminium alloy (Mortensen et al., 2026, Table 1)
# ──────────────────────────────────────────────────────────────────────────────
T_INIT   = 540.0        # °C  initial temperature (uniform, after soaking)
T_WATER  = 20.0         # °C  quench bath temperature
DELTA_T  = T_INIT - T_WATER   # 520 °C  temperature scale
K_THERM  = 160.0        # W/(m·K)  thermal conductivity
RHO_CP   = 2.4e6        # J/(m³·K) volumetric heat capacity
H_CONV   = 4000.0       # W/(m²·K) convection coefficient (water quench)
ALPHA    = K_THERM / RHO_CP   # m²/s  ≈ 6.67e-5  thermal diffusivity


# ══════════════════════════════════════════════════════════════════════════════
# Helper: 1D Plane Wall — reused by Rectangular3D, Cylinder3D, StackedCubes3D
# ══════════════════════════════════════════════════════════════════════════════

class PlaneWall1D:
    """
    1D plane wall transient solution — symmetric cooling from both faces.

    Governing equation:  ∂θ/∂t = α ∂²θ/∂x²
    Boundary condition:  -k ∂θ/∂x = h·θ  at x = L  (and symmetrically at x = 0)

    The separation-of-variables solution is (Carslaw & Jaeger, 1959, §3.8):
        θ(x*, Fo) = Σ_n C_n · cos(ζ_n · x*) · exp(−ζ_n² · Fo)

    where x* = (x − L/2)/(L/2) ∈ [−1, 1] is the centred coordinate,
    Fo = α·t/(L/2)² is the Fourier number, and ζ_n satisfies:
        ζ_n · tan(ζ_n) = Bi  with  Bi = h·(L/2)/k

    Coefficient:  C_n = 4·sin(ζ_n) / (2·ζ_n + sin(2·ζ_n))

    We use N eigenvalues (default 20); all eigenvalues beyond the first are
    negligible after approximately Fo > 0.2 (i.e., about 1.5 s for the
    A356 rectanglar prism at these dimensions).
    """

    def __init__(self, L: float, h: float = H_CONV, k: float = K_THERM,
                 alpha: float = ALPHA, N: int = 20):
        self.L     = L
        self.a     = L / 2          # half-thickness
        self.Bi    = h * self.a / k
        self.alpha = alpha
        self.N     = N
        self._compute_eigenvalues()

    def _compute_eigenvalues(self):
        """Solve ζ·tan(ζ) = Bi for the first N roots using Brent's method."""
        self.zeta = np.zeros(self.N)
        self.C    = np.zeros(self.N)
        for n in range(self.N):
            # Root of n-th mode lies in (n·π, (n+0.5)·π)
            lo = n * np.pi + 1e-10
            hi = (n + 0.5) * np.pi - 1e-10
            try:
                z = brentq(lambda z: z * np.tan(z) - self.Bi, lo, hi)
            except ValueError:
                z = (lo + hi) / 2   # fallback for extreme Bi
            self.zeta[n] = z
            self.C[n] = 4.0 * np.sin(z) / (2.0 * z + np.sin(2.0 * z))

    def theta(self, x: np.ndarray, t: float) -> np.ndarray:
        """
        Dimensionless temperature θ = (T − T_w)/(T_0 − T_w) at position x ∈ [0, L].
        """
        x_star = (np.asarray(x, dtype=float) - self.a) / self.a
        Fo     = self.alpha * t / self.a ** 2
        result = np.zeros_like(x_star)
        for n in range(self.N):
            result += (self.C[n]
                       * np.cos(self.zeta[n] * x_star)
                       * np.exp(-self.zeta[n] ** 2 * Fo))
        return result


# ══════════════════════════════════════════════════════════════════════════════
# Domain 1: 3D Rectangular Prism
# ══════════════════════════════════════════════════════════════════════════════

class Rectangular3D:
    """
    3D rectangular prism with Robin BC on all six faces.

    Solution strategy: product (separation) of three independent 1D plane-wall
    solutions, which is exact when the initial condition is uniform and the
    Robin BC coefficient h is the same on all faces — both hold here.

        T(x, y, z, t) = T_w + ΔT · θ_x(x,t) · θ_y(y,t) · θ_z(z,t)

    Dimensions follow the A356 automotive subframe cross-section from
    Mortensen et al. (2026), Section 2.1:
        Lx = 1.3 m, Ly = 0.6 m, Lz = 0.4 m
        Bi_x ≈ 16.3, Bi_y ≈ 7.5, Bi_z ≈ 5.0
    """

    name  = "Rectangular Prism 3D"
    color = "#1565C0"

    def __init__(self, Lx: float = 1.3, Ly: float = 0.6, Lz: float = 0.4,
                 h: float = H_CONV, k: float = K_THERM,
                 alpha: float = ALPHA, N: int = 8):
        self.Lx, self.Ly, self.Lz = Lx, Ly, Lz
        self.h     = h
        self.alpha = alpha
        self.wx = PlaneWall1D(Lx, h, k, alpha, N)
        self.wy = PlaneWall1D(Ly, h, k, alpha, N)
        self.wz = PlaneWall1D(Lz, h, k, alpha, N)
        self.Bi = dict(x=h * (Lx / 2) / k,
                       y=h * (Ly / 2) / k,
                       z=h * (Lz / 2) / k)

    def theta(self, x, y, z, t):
        """Dimensionless temperature θ ∈ [0, 1]."""
        return self.wx.theta(x, t) * self.wy.theta(y, t) * self.wz.theta(z, t)

    def T(self, x, y, z, t):
        """Physical temperature T (°C)."""
        return T_WATER + DELTA_T * self.theta(x, y, z, t)

    def mask(self, x, y, z):
        return ((x >= 0) & (x <= self.Lx) &
                (y >= 0) & (y <= self.Ly) &
                (z >= 0) & (z <= self.Lz))

    # ── Sampling methods required by the PINN trainer ────────────────────────

    def sample_interior(self, n: int, rng=None):
        """Uniform random interior samples: returns (x, y, z) each shape (n,)."""
        rng = rng or np.random.default_rng(0)
        x = rng.uniform(0, self.Lx, n).astype(np.float32)
        y = rng.uniform(0, self.Ly, n).astype(np.float32)
        z = rng.uniform(0, self.Lz, n).astype(np.float32)
        return x, y, z

    def sample_boundary(self, n: int, rng=None):
        """
        Sample boundary points on all 6 faces with outward unit normals.
        Points are distributed proportionally to face area for even coverage.

        Returns: (bx, by, bz, nx, ny, nz) each shape (n,).
        """
        rng = rng or np.random.default_rng(1)
        Lx, Ly, Lz = self.Lx, self.Ly, self.Lz

        # Face areas and their outward normals
        faces = [
            # (normal_vec, fixed_axis, fixed_val, ranges)
            ((-1, 0, 0), 0, 0.0,  [(1, Ly), (2, Lz)]),   # x=0  face
            ((+1, 0, 0), 0, Lx,   [(1, Ly), (2, Lz)]),   # x=Lx face
            ((0, -1, 0), 1, 0.0,  [(0, Lx), (2, Lz)]),   # y=0  face
            ((0, +1, 0), 1, Ly,   [(0, Lx), (2, Lz)]),   # y=Ly face
            ((0, 0, -1), 2, 0.0,  [(0, Lx), (1, Ly)]),   # z=0  face
            ((0, 0, +1), 2, Lz,   [(0, Lx), (1, Ly)]),   # z=Lz face
        ]
        areas = [Ly * Lz, Ly * Lz, Lx * Lz, Lx * Lz, Lx * Ly, Lx * Ly]
        total_area = sum(areas)
        counts = [max(1, round(n * a / total_area)) for a in areas]
        # Correct rounding error so total == n
        diff = n - sum(counts)
        counts[0] += diff

        bx_all, by_all, bz_all = [], [], []
        nx_all, ny_all, nz_all = [], [], []

        for (norm, fixed_ax, fixed_val, free_axes), cnt in zip(faces, counts):
            c = max(1, cnt)
            pts = np.zeros((c, 3), dtype=np.float32)
            pts[:, fixed_ax] = fixed_val
            for ax, L in free_axes:
                pts[:, ax] = rng.uniform(0, L, c).astype(np.float32)
            bx_all.append(pts[:, 0])
            by_all.append(pts[:, 1])
            bz_all.append(pts[:, 2])
            nx_all.append(np.full(c, norm[0], dtype=np.float32))
            ny_all.append(np.full(c, norm[1], dtype=np.float32))
            nz_all.append(np.full(c, norm[2], dtype=np.float32))

        return (np.concatenate(bx_all), np.concatenate(by_all),
                np.concatenate(bz_all), np.concatenate(nx_all),
                np.concatenate(ny_all), np.concatenate(nz_all))

    def info(self):
        return (f"Rectangular3D  {self.Lx}×{self.Ly}×{self.Lz} m\n"
                f"  Bi_x={self.Bi['x']:.2f}  Bi_y={self.Bi['y']:.2f}"
                f"  Bi_z={self.Bi['z']:.2f}")


# ══════════════════════════════════════════════════════════════════════════════
# Domain 2: 3D Cylinder
# ══════════════════════════════════════════════════════════════════════════════

class Cylinder3D:
    """
    3D cylinder with Robin BC on the lateral surface and on both endcaps.

    Because the cylinder is axially symmetric, the solution separates into
    radial (Bessel) and axial (plane-wall) factors:

        T(r, z, t) = T_w + ΔT · θ_r(r, t) · θ_z(z, t)

    Radial part — Bessel J₀ eigenseries (Carslaw & Jaeger, 1959, §7.8):
        θ_r(r, t) = Σ_n C_n · J₀(λ_n · r) · exp(−λ_n² · α · t)
    where eigenvalues satisfy:  λ_n · R · J₁(λ_n R) = Bi_r · J₀(λ_n R)
    and C_n = 2 J₁(λ_n R) / [λ_n R (J₀²(λ_n R) + J₁²(λ_n R))]

    Axial part — standard plane-wall solution θ_z(z, t) (see PlaneWall1D).

    Default geometry — cylindrical casting component:
        R = 0.15 m,  Hz = 0.40 m
        Bi_r = h·R/k ≈ 3.75,  Bi_z = h·(Hz/2)/k ≈ 2.5
    """

    name  = "Cylinder 3D"
    color = "#2E7D32"

    def __init__(self, R: float = 0.15, Hz: float = 0.4,
                 h: float = H_CONV, k: float = K_THERM,
                 alpha: float = ALPHA, N: int = 8):
        self.R     = R
        self.Hz    = Hz
        # Bounding box attributes (used by trainer for coordinate normalisation)
        self.Lx    = 2 * R
        self.Ly    = 2 * R
        self.Lz    = Hz
        self.h     = h
        self.alpha = alpha
        self.Bi_r  = h * R / k
        self.Bi_z  = h * (Hz / 2) / k
        self.N     = N
        self._compute_radial_eigenvalues(h, k)
        self.wz = PlaneWall1D(Hz, h, k, alpha, N)

    def _compute_radial_eigenvalues(self, h: float, k: float):
        """
        First N roots of  λ_n · R · J₁(λ_n R) = Bi_r · J₀(λ_n R).
        These are found numerically using Brent's method on bracketed intervals.
        """
        Bi = self.Bi_r
        R  = self.R
        self.lam   = np.zeros(self.N)
        self.C_rad = np.zeros(self.N)
        for n in range(self.N):
            lo = (n * np.pi + 1e-10) / R
            hi = ((n + 1) * np.pi - 1e-10) / R
            def eq(lam, B=Bi, r=R):
                return lam * r * j1(lam * r) - B * j0(lam * r)
            try:
                ln = brentq(eq, lo, hi)
            except ValueError:
                ln = (lo + hi) / 2
            self.lam[n] = ln
            J0v  = j0(ln * R)
            J1v  = j1(ln * R)
            denom = ln * R * (J0v ** 2 + J1v ** 2)
            self.C_rad[n] = 2.0 * J1v / denom if denom != 0 else 0.0

    def theta_r(self, r: np.ndarray, t: float) -> np.ndarray:
        """Radial dimensionless temperature θ_r(r, t)."""
        r = np.asarray(r, dtype=float)
        result = np.zeros_like(r)
        for n in range(self.N):
            ln = self.lam[n]
            result += (self.C_rad[n]
                       * j0(ln * r)
                       * np.exp(-ln ** 2 * self.alpha * t))
        return result

    def T(self, x, y, z, t):
        """T(x, y, z, t) — Cartesian input, cylindrical evaluation."""
        r = np.sqrt(np.asarray(x) ** 2 + np.asarray(y) ** 2)
        return T_WATER + DELTA_T * self.theta_r(r, t) * self.wz.theta(z, t)

    def mask(self, x, y, z):
        r = np.sqrt(np.asarray(x) ** 2 + np.asarray(y) ** 2)
        return (r <= self.R) & (np.asarray(z) >= 0) & (np.asarray(z) <= self.Hz)

    # ── Sampling methods ─────────────────────────────────────────────────────

    def sample_interior(self, n: int, rng=None):
        """
        Uniform samples inside the cylinder via rejection sampling in the
        bounding square [−R, R]² × [0, Hz].
        """
        rng = rng or np.random.default_rng(0)
        pts = []
        while len(pts) < n:
            batch = int((n - len(pts)) * 1.5) + 10
            x = rng.uniform(-self.R, self.R, batch)
            y = rng.uniform(-self.R, self.R, batch)
            z = rng.uniform(0, self.Hz, batch)
            inside = (x ** 2 + y ** 2) <= self.R ** 2
            for xi, yi, zi in zip(x[inside], y[inside], z[inside]):
                pts.append((xi, yi, zi))
                if len(pts) == n:
                    break
        pts = np.array(pts[:n], dtype=np.float32)
        return pts[:, 0], pts[:, 1], pts[:, 2]

    def sample_boundary(self, n: int, rng=None):
        """
        Sample boundary points on the three surfaces:
          - Lateral surface (side): r = R, θ ∈ [0, 2π], z ∈ [0, Hz]
          - Bottom cap (z = 0):    r ∈ [0, R], θ ∈ [0, 2π]
          - Top cap (z = Hz):      same as bottom

        Normal vectors: lateral → radial outward, caps → ±ẑ.
        """
        rng = rng or np.random.default_rng(1)
        # Distribute points proportional to surface area
        lateral_area = 2 * np.pi * self.R * self.Hz
        cap_area     = np.pi * self.R ** 2
        total_area   = lateral_area + 2 * cap_area
        n_lat        = max(1, round(n * lateral_area / total_area))
        n_cap        = max(1, (n - n_lat) // 2)
        n_lat        = max(1, n - 2 * n_cap)

        # Lateral surface
        phi_lat = rng.uniform(0, 2 * np.pi, n_lat).astype(np.float32)
        z_lat   = rng.uniform(0, self.Hz,   n_lat).astype(np.float32)
        bx_lat  = self.R * np.cos(phi_lat)
        by_lat  = self.R * np.sin(phi_lat)
        bz_lat  = z_lat
        nx_lat  = np.cos(phi_lat)   # radial outward
        ny_lat  = np.sin(phi_lat)
        nz_lat  = np.zeros(n_lat, dtype=np.float32)

        # Bottom cap (z = 0, normal = −ẑ)
        r_bot   = self.R * np.sqrt(rng.uniform(0, 1, n_cap).astype(np.float32))
        phi_bot = rng.uniform(0, 2 * np.pi, n_cap).astype(np.float32)
        bx_bot  = r_bot * np.cos(phi_bot)
        by_bot  = r_bot * np.sin(phi_bot)

        # Top cap (z = Hz, normal = +ẑ)
        r_top   = self.R * np.sqrt(rng.uniform(0, 1, n_cap).astype(np.float32))
        phi_top = rng.uniform(0, 2 * np.pi, n_cap).astype(np.float32)
        bx_top  = r_top * np.cos(phi_top)
        by_top  = r_top * np.sin(phi_top)

        bx = np.concatenate([bx_lat, bx_bot, bx_top])
        by = np.concatenate([by_lat, by_bot, by_top])
        bz = np.concatenate([bz_lat,
                             np.zeros(n_cap, dtype=np.float32),
                             np.full(n_cap, self.Hz, dtype=np.float32)])
        nx = np.concatenate([nx_lat,
                             np.zeros(n_cap, dtype=np.float32),
                             np.zeros(n_cap, dtype=np.float32)])
        ny = np.concatenate([ny_lat,
                             np.zeros(n_cap, dtype=np.float32),
                             np.zeros(n_cap, dtype=np.float32)])
        nz = np.concatenate([nz_lat,
                             np.full(n_cap, -1.0, dtype=np.float32),
                             np.full(n_cap, +1.0, dtype=np.float32)])
        return bx, by, bz, nx, ny, nz

    def info(self):
        return (f"Cylinder3D  R={self.R} m  Hz={self.Hz} m\n"
                f"  Bi_r={self.Bi_r:.2f}  Bi_z={self.Bi_z:.2f}")


# ══════════════════════════════════════════════════════════════════════════════
# Domain 3: Stacked Cubes (Shen et al., 2023 benchmark geometry)
# ══════════════════════════════════════════════════════════════════════════════

class StackedCubes3D:
    """
    N square prisms stacked along the z-axis — same material throughout.

    Because the material is homogeneous, the solution reduces to a single
    tall prism of dimensions L_cube × L_cube × (N_stack · L_cube), and the
    analytical product solution from Rectangular3D applies directly.

    This geometry tests PINN generalisation when the aspect ratio is very
    different from the training domain. The stacking interface (z = L_cube)
    is geometrically marked for visualisation but has no physical discontinuity.

    Default: 2 cubes × 0.5 m → 0.5 × 0.5 × 1.0 m
        Bi = h·(0.25)/k ≈ 6.25  (same in all directions — high symmetry)

    Reference: Shen et al. (2023), benchmark geometry B3.
    """

    name  = "Stacked Cubes 3D"
    color = "#E65100"

    def __init__(self, L_cube: float = 0.5, N_stack: int = 2,
                 h: float = H_CONV, k: float = K_THERM,
                 alpha: float = ALPHA, N_terms: int = 8):
        self.L_cube  = L_cube
        self.N_stack = N_stack
        self.Lx      = L_cube
        self.Ly      = L_cube
        self.Lz      = L_cube * N_stack
        self.h       = h
        self.alpha   = alpha
        # Delegate to Rectangular3D for the physics
        self._rect = Rectangular3D(
            Lx=L_cube, Ly=L_cube, Lz=self.Lz,
            h=h, k=k, alpha=alpha, N=N_terms)
        self.interface_z = [L_cube * i for i in range(1, N_stack)]

    def T(self, x, y, z, t):
        return self._rect.T(x, y, z, t)

    def theta(self, x, y, z, t):
        return self._rect.theta(x, y, z, t)

    def mask(self, x, y, z):
        return ((np.asarray(x) >= 0) & (np.asarray(x) <= self.L_cube) &
                (np.asarray(y) >= 0) & (np.asarray(y) <= self.L_cube) &
                (np.asarray(z) >= 0) & (np.asarray(z) <= self.Lz))

    def sample_interior(self, n: int, rng=None):
        return self._rect.sample_interior(n, rng=rng)

    def sample_boundary(self, n: int, rng=None):
        return self._rect.sample_boundary(n, rng=rng)

    def info(self):
        Bi = H_CONV * (self.L_cube / 2) / K_THERM
        return (f"StackedCubes3D  {self.N_stack}×[{self.L_cube} m cube]"
                f"  →  {self.L_cube}×{self.L_cube}×{self.Lz} m\n"
                f"  Bi={Bi:.2f}  (isotropic — same in all directions)")


# ══════════════════════════════════════════════════════════════════════════════
# Domain 4: L-Shape 3D  (Explicit finite-difference reference)
# ══════════════════════════════════════════════════════════════════════════════

class LShape3D:
    """
    3D L-shaped prism — no closed-form solution, solved by explicit FD.

    Cross-section (xy-plane):  (x ≤ cut_x) ∪ (y ≤ cut_y)
    Extruded uniformly over z ∈ [0, Lz].

    This geometry is representative of T-junction nodes in automotive
    subframe castings where two rib walls intersect at right angles.
    The L-shape breaks the separability required for the product solution,
    so a numerical reference is necessary (Incropera et al., 2007, §4.5).

    Numerical method: 3D explicit finite-difference on a cell-centred grid.
    Stability criterion:  Δt < 1 / (2α Σ(1/Δh²) + 6h/(ρCp·Δh_min))
    We use 40% of the maximum stable time step for margin.

    The FD solution is precomputed at all 21 FEM checkpoints (t = 0, 1.5, …, 30 s)
    and stored as a RegularGridInterpolator for fast lookups during training.

    Default dimensions (complex asymmetric casting node):
        Lx = Ly = 0.8 m, Lz = 0.4 m
        cut_x = cut_y = 0.3 m  (removes the top-right quadrant)
    """

    name  = "L-Shape 3D"
    color = "#6A1B9A"

    # FEM time checkpoints — must match the training loop (DT_FEM = 1.5 s)
    T_FEM = np.arange(0.0, 30.0 + 1e-9, 1.5)   # 21 steps

    def __init__(self, Lx: float = 0.8, Ly: float = 0.8, Lz: float = 0.4,
                 cut_x: float = 0.3, cut_y: float = 0.3,
                 h: float = H_CONV, k: float = K_THERM,
                 alpha: float = ALPHA, rho_cp: float = RHO_CP,
                 nx: int = 20, ny: int = 20, nz: int = 10,
                 solve_reference: bool = True):
        self.Lx, self.Ly, self.Lz = Lx, Ly, Lz
        self.cut_x, self.cut_y    = cut_x, cut_y
        self.h, self.k            = h, k
        self.alpha, self.rho_cp   = alpha, rho_cp
        self.nx, self.ny, self.nz = nx, ny, nz

        # Cell-centred uniform grid
        dx, dy, dz     = Lx / nx, Ly / ny, Lz / nz
        self.dx, self.dy, self.dz = dx, dy, dz
        self.xi_c = np.linspace(dx / 2, Lx - dx / 2, nx)
        self.yi_c = np.linspace(dy / 2, Ly - dy / 2, ny)
        self.zi_c = np.linspace(dz / 2, Lz - dz / 2, nz)

        # 3D boolean mask on the cell-centred grid
        XX, YY, ZZ  = np.meshgrid(self.xi_c, self.yi_c, self.zi_c, indexing='ij')
        self.inside = self._mask_3d(XX, YY, ZZ)

        # Nearest-inside-cell index map — used to fill exterior grid cells
        # with the temperature of the nearest interior cell (avoids NaN
        # propagation into the interpolator).
        self._nn_idx = distance_transform_edt(
            ~self.inside, return_distances=False, return_indices=True)

        self._T_cache = None
        self._interp = None
        if solve_reference:
            print(f"  LShape3D: running FD solver ({nx}×{ny}×{nz} grid)…", flush=True)
            self._T_cache = self._run_fd()   # shape (nx, ny, nz, n_t_fem)

            self._interp = RegularGridInterpolator(
                (self.xi_c, self.yi_c, self.zi_c, self.T_FEM),
                self._T_cache,
                method='linear',
                bounds_error=False,
                fill_value=np.nan,
            )
            print("  LShape3D: FD solver done.", flush=True)

    # ── Geometry ─────────────────────────────────────────────────────────────

    def _mask_3d(self, x, y, z):
        """Return True where the cell is inside the L-shape."""
        return (((x <= self.cut_x) | (y <= self.cut_y)) &
                (z >= 0) & (z <= self.Lz))

    def mask(self, x, y, z):
        x, y, z = np.asarray(x), np.asarray(y), np.asarray(z)
        return (((x <= self.cut_x) | (y <= self.cut_y)) &
                (x >= 0) & (x <= self.Lx) &
                (y >= 0) & (y <= self.Ly) &
                (z >= 0) & (z <= self.Lz))

    # ── Finite-difference solver ──────────────────────────────────────────────

    def _fd_step(self, T: np.ndarray, dt: float) -> np.ndarray:
        """
        One explicit FD update.
        Interior cells: standard second-order Laplacian (conduction).
        Exposed-face cells: Robin BC via ghost-cell approximation:
            q_conv = h · (T_w − T) / (ρCp · Δh)
        """
        ins = self.inside
        dT  = np.zeros_like(T)
        for axis, dh in enumerate([self.dx, self.dy, self.dz]):
            for shift in (+1, -1):
                T_n   = np.roll(T,   shift, axis=axis)
                ins_n = np.roll(ins, shift, axis=axis).copy()
                # Wrapped edge of roll is not a real neighbour — mark invalid
                idx = [slice(None)] * 3
                idx[axis] = 0 if shift == +1 else -1
                ins_n[tuple(idx)] = False
                # Conduction flux (both cells inside)
                dT += np.where(ins & ins_n,
                               self.alpha / dh ** 2 * (T_n - T), 0.0)
                # Convection at exposed face (current inside, neighbour outside)
                dT += np.where(ins & ~ins_n,
                               self.h / (self.rho_cp * dh) * (T_WATER - T), 0.0)
        return np.where(ins, T + dt * dT, T)

    def _run_fd(self) -> np.ndarray:
        """
        Integrate from T_init to T_FEM[-1], storing snapshots at each
        FEM checkpoint.  Returns array of shape (nx, ny, nz, n_t_fem).
        """
        dx, dy, dz   = self.dx, self.dy, self.dz
        sum_inv_dh2  = 1 / dx ** 2 + 1 / dy ** 2 + 1 / dz ** 2
        dh_min       = min(dx, dy, dz)
        dt_max       = 1.0 / (2 * self.alpha * sum_inv_dh2
                              + 6 * self.h / (self.rho_cp * dh_min))
        dt           = dt_max * 0.40   # 40% of stability limit

        T = np.where(self.inside, float(T_INIT), np.nan)

        n_t     = len(self.T_FEM)
        T_cache = np.zeros((self.nx, self.ny, self.nz, n_t))
        T_cache[:, :, :, 0] = self._fill_nearest(T)

        t_now, store_idx = 0.0, 1
        n_max = int(np.ceil(self.T_FEM[-1] / dt)) + 20

        for _ in range(n_max):
            if store_idx >= n_t:
                break
            T      = self._fd_step(T, dt)
            t_now += dt
            while store_idx < n_t and t_now >= self.T_FEM[store_idx] - 1e-9:
                T_cache[:, :, :, store_idx] = self._fill_nearest(T)
                store_idx += 1

        return T_cache

    def _fill_nearest(self, T: np.ndarray) -> np.ndarray:
        """Replace NaN (exterior cells) with nearest interior cell value."""
        ni = self._nn_idx
        return T[ni[0], ni[1], ni[2]]

    # ── Temperature query ─────────────────────────────────────────────────────

    def T(self, x, y, z, t):
        """
        T(x, y, z, t) — trilinearly interpolated from the FD cache.
        Returns NaN for points outside the L-shape mask.
        """
        if self._interp is None:
            raise RuntimeError("LShape3D reference cache was disabled for this instance.")
        x, y, z = np.asarray(x, float), np.asarray(y, float), np.asarray(z, float)
        scalar  = (x.ndim == 0)
        x, y, z = np.atleast_1d(x), np.atleast_1d(y), np.atleast_1d(z)
        t_arr   = np.full_like(x, float(t))

        xq = np.clip(x,     self.xi_c[0], self.xi_c[-1])
        yq = np.clip(y,     self.yi_c[0], self.yi_c[-1])
        zq = np.clip(z,     self.zi_c[0], self.zi_c[-1])
        tq = np.clip(t_arr, self.T_FEM[0], self.T_FEM[-1])

        pts   = np.stack([xq, yq, zq, tq], axis=-1)
        T_out = self._interp(pts)
        T_out = np.where(self.mask(x, y, z), T_out, np.nan)
        return float(T_out[0]) if scalar else T_out

    def theta(self, x, y, z, t):
        """Dimensionless temperature θ = (T − T_w)/ΔT, clipped to [0, 1]."""
        return np.clip((self.T(x, y, z, t) - T_WATER) / DELTA_T, 0.0, 1.0)

    # ── Sampling methods ─────────────────────────────────────────────────────

    def sample_interior(self, n: int, rng=None, corner_frac: float = 0.35):
        """
        Stratified samples inside the L-shape.

        (1-corner_frac) of points: uniform over the full bounding box (rejection).
        corner_frac of points: concentrated near the re-entrant corner (cut_x, cut_y)
            where the 270-degree angle produces the steepest thermal gradients.
        """
        rng = rng or np.random.default_rng(0)

        def _rejection(n_req):
            pts = []
            while len(pts) < n_req:
                batch = int((n_req - len(pts)) * 1.5) + 10
                x = rng.uniform(0, self.Lx, batch)
                y = rng.uniform(0, self.Ly, batch)
                z = rng.uniform(0, self.Lz, batch)
                inside = self.mask(x, y, z)
                for xi, yi, zi in zip(x[inside], y[inside], z[inside]):
                    pts.append((xi, yi, zi))
                    if len(pts) == n_req:
                        break
            return np.array(pts[:n_req], dtype=np.float32)

        n_corner  = int(n * corner_frac)
        n_uniform = n - n_corner

        uniform_pts = _rejection(n_uniform)

        # Corner region: Gaussian cloud around (cut_x, cut_y) clipped to L-shape
        cx, cy = self.cut_x, self.cut_y
        radius = min(self.Lx, self.Ly) * 0.25   # ≈ half-width of focus zone
        corner_pts = []
        while len(corner_pts) < n_corner:
            batch = (n_corner - len(corner_pts)) * 4 + 10
            x = rng.normal(cx, radius, batch).astype(np.float32)
            y = rng.normal(cy, radius, batch).astype(np.float32)
            z = rng.uniform(0, self.Lz, batch).astype(np.float32)
            x = np.clip(x, 0, self.Lx)
            y = np.clip(y, 0, self.Ly)
            inside = self.mask(x, y, z)
            for xi, yi, zi in zip(x[inside], y[inside], z[inside]):
                corner_pts.append((xi, yi, zi))
                if len(corner_pts) == n_corner:
                    break
        corner_pts = np.array(corner_pts[:n_corner], dtype=np.float32)

        pts = np.concatenate([uniform_pts, corner_pts], axis=0)
        # Shuffle so corner/uniform points are interleaved (avoids batch bias)
        rng.shuffle(pts)
        return pts[:, 0], pts[:, 1], pts[:, 2]

    def sample_boundary(self, n: int, rng=None):
        """
        Sample the 10 boundary faces of the L-shape uniformly.

        The L-shape boundary consists of:
          - 8 vertical faces (4 outer + 2 inner cut walls), each extruded over z
          - 2 horizontal faces (bottom z=0, top z=Lz) — L-shaped cross-section

        Outward normals are assigned per face.
        """
        rng = rng or np.random.default_rng(1)
        cx, cy  = self.cut_x, self.cut_y
        Lx, Ly  = self.Lx, self.Ly
        Lz      = self.Lz

        # Vertical faces: (x0, x1, y0, y1, nx_val, ny_val)
        # Outer boundary edges of the L
        v_faces = [
            (0.0,  0.0,  0.0,  Ly,   -1,  0),   # x=0 left wall  (full height y)
            (0.0,  cx,   Ly,   Ly,    0, +1),   # y=Ly top  (partial: x ≤ cut_x)
            (cx,   cx,   cy,   Ly,   +1,  0),   # x=cut_x inner vertical wall
            (cx,   Lx,   cy,   cy,    0, -1),   # y=cut_y inner horizontal wall
            (Lx,   Lx,   0.0,  cy,   +1,  0),   # x=Lx right wall (partial: y ≤ cut_y)
            (0.0,  Lx,   0.0,  0.0,   0, -1),   # y=0 bottom wall (full width x)
        ]
        # Each face spans z ∈ [0, Lz]
        # Length of each vertical face edge:
        v_lengths = [Ly, cx, Ly - cy, Lx - cx, cy, Lx]
        v_areas   = [l * Lz for l in v_lengths]

        # Horizontal cross-section area: Lx*Ly − (Lx−cx)*(Ly−cy)
        h_area = Lx * Ly - (Lx - cx) * (Ly - cy)

        total_area = sum(v_areas) + 2 * h_area
        # Allocate sample counts proportional to area
        counts_v = [max(1, round(n * a / total_area)) for a in v_areas]
        n_h_each = max(1, round(n * h_area / total_area))
        n_h_each = max(1, (n - sum(counts_v)) // 2)
        diff = n - sum(counts_v) - 2 * n_h_each
        counts_v[0] += diff

        bx_all, by_all, bz_all = [], [], []
        nx_all, ny_all, nz_all = [], [], []

        for (x0, x1, y0, y1, nxv, nyv), cnt in zip(v_faces, counts_v):
            c = max(1, cnt)
            if x0 == x1:   # vertical face at fixed x
                xs = np.full(c, x0, dtype=np.float32)
                ys = rng.uniform(y0, y1, c).astype(np.float32)
            else:          # horizontal face at fixed y
                xs = rng.uniform(x0, x1, c).astype(np.float32)
                ys = np.full(c, y0, dtype=np.float32)
            zs = rng.uniform(0, Lz, c).astype(np.float32)
            bx_all.append(xs); by_all.append(ys); bz_all.append(zs)
            nx_all.append(np.full(c, float(nxv), dtype=np.float32))
            ny_all.append(np.full(c, float(nyv), dtype=np.float32))
            nz_all.append(np.zeros(c, dtype=np.float32))

        # Bottom face (z=0, normal=−ẑ) — L-shaped, sample by rejection
        pts_bot = []
        while len(pts_bot) < n_h_each:
            batch = int((n_h_each - len(pts_bot)) * 1.5) + 5
            xb = rng.uniform(0, Lx, batch)
            yb = rng.uniform(0, Ly, batch)
            ok = self.mask(xb, yb, np.zeros(batch))
            for xi, yi in zip(xb[ok], yb[ok]):
                pts_bot.append((xi, yi))
                if len(pts_bot) == n_h_each:
                    break
        pts_bot = np.array(pts_bot[:n_h_each], dtype=np.float32)
        bx_all.append(pts_bot[:, 0]); by_all.append(pts_bot[:, 1])
        bz_all.append(np.zeros(n_h_each, dtype=np.float32))
        nx_all.append(np.zeros(n_h_each, dtype=np.float32))
        ny_all.append(np.zeros(n_h_each, dtype=np.float32))
        nz_all.append(np.full(n_h_each, -1.0, dtype=np.float32))

        # Top face (z=Lz, normal=+ẑ) — same L-shaped region
        pts_top = []
        while len(pts_top) < n_h_each:
            batch = int((n_h_each - len(pts_top)) * 1.5) + 5
            xb = rng.uniform(0, Lx, batch)
            yb = rng.uniform(0, Ly, batch)
            ok = self.mask(xb, yb, np.zeros(batch))
            for xi, yi in zip(xb[ok], yb[ok]):
                pts_top.append((xi, yi))
                if len(pts_top) == n_h_each:
                    break
        pts_top = np.array(pts_top[:n_h_each], dtype=np.float32)
        bx_all.append(pts_top[:, 0]); by_all.append(pts_top[:, 1])
        bz_all.append(np.full(n_h_each, Lz, dtype=np.float32))
        nx_all.append(np.zeros(n_h_each, dtype=np.float32))
        ny_all.append(np.zeros(n_h_each, dtype=np.float32))
        nz_all.append(np.full(n_h_each, +1.0, dtype=np.float32))

        return (np.concatenate(bx_all), np.concatenate(by_all),
                np.concatenate(bz_all), np.concatenate(nx_all),
                np.concatenate(ny_all), np.concatenate(nz_all))

    def info(self):
        vol_frac = self.inside.sum() / self.inside.size
        return (f"LShape3D  {self.Lx}×{self.Ly}×{self.Lz} m  "
                f"(cut x>{self.cut_x}, y>{self.cut_y})  "
                f"vol≈{vol_frac:.0%} of bbox\n"
                f"  Numerical FD grid: {self.nx}×{self.ny}×{self.nz}")


class SubframeLike3D:
    """
    Paper-inspired synthetic automotive subframe benchmark.

    This is not the proprietary paper mesh. It is a compact surrogate that
    keeps the thermal/PINN difficulty we care about before real CAD/FEM data is
    available: thin rails, cross-members, mounting bosses, support/contact pads,
    and reduced-cooling internal cavities.
    """

    name = "Paper-inspired Subframe-like 3D"
    color = "#455A64"

    def __init__(
        self,
        Lx: float = 1.30,
        Ly: float = 0.65,
        Lz: float = 0.32,
        h: float = H_CONV,
        alpha: float = ALPHA,
    ):
        self.Lx, self.Ly, self.Lz = Lx, Ly, Lz
        self.h = h
        self.alpha = alpha

        rail_w = 0.115
        rail_z0, rail_z1 = 0.115, 0.225
        cross_w = 0.135
        self.boxes = [
            # Long side rails
            (0.06, Lx - 0.06, 0.08, 0.08 + rail_w, rail_z0, rail_z1),
            (0.06, Lx - 0.06, Ly - 0.08 - rail_w, Ly - 0.08, rail_z0, rail_z1),
            # Cross-members
            (0.16, 0.16 + cross_w, 0.08, Ly - 0.08, rail_z0, rail_z1),
            (0.58, 0.58 + cross_w, 0.11, Ly - 0.11, rail_z0, rail_z1),
            (1.00, 1.00 + cross_w, 0.08, Ly - 0.08, rail_z0, rail_z1),
            # Lower support ribs
            (0.30, 1.00, 0.285, 0.365, 0.055, rail_z0),
            (0.60, 0.72, 0.18, 0.47, 0.055, rail_z0),
        ]
        self.cylinders = [
            (0.16, 0.135, 0.070, 0.055, 0.300),
            (1.14, 0.135, 0.070, 0.055, 0.300),
            (0.16, Ly - 0.135, 0.070, 0.055, 0.300),
            (1.14, Ly - 0.135, 0.070, 0.055, 0.300),
        ]
        self.support_boxes = [
            (0.10, 0.23, 0.075, 0.195, 0.000, 0.060),
            (1.07, 1.20, 0.075, 0.195, 0.000, 0.060),
            (0.10, 0.23, Ly - 0.195, Ly - 0.075, 0.000, 0.060),
            (1.07, 1.20, Ly - 0.195, Ly - 0.075, 0.000, 0.060),
        ]
        self.cavity_boxes = [
            (0.36, 0.52, 0.245, 0.405, 0.105, 0.235),
            (0.78, 0.94, 0.245, 0.405, 0.105, 0.235),
        ]
        self._all_boxes = self.boxes + self.support_boxes

    @staticmethod
    def _inside_box(x, y, z, box):
        x0, x1, y0, y1, z0, z1 = box
        return (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1) & (z >= z0) & (z <= z1)

    @staticmethod
    def _inside_cylinder(x, y, z, cyl):
        cx, cy, r, z0, z1 = cyl
        return ((x - cx) ** 2 + (y - cy) ** 2 <= r ** 2) & (z >= z0) & (z <= z1)

    def mask(self, x, y, z):
        x = np.asarray(x)
        y = np.asarray(y)
        z = np.asarray(z)
        inside = np.zeros(np.broadcast_shapes(x.shape, y.shape, z.shape), dtype=bool)
        xb, yb, zb = np.broadcast_arrays(x, y, z)
        for box in self._all_boxes:
            inside |= self._inside_box(xb, yb, zb, box)
        for cyl in self.cylinders:
            inside |= self._inside_cylinder(xb, yb, zb, cyl)
        for cav in self.cavity_boxes:
            inside &= ~self._inside_box(xb, yb, zb, cav)
        return inside

    def sample_interior(self, n: int, rng=None):
        rng = rng or np.random.default_rng(0)
        pts = []
        while len(pts) < n:
            batch = max(256, int((n - len(pts)) * 4.0))
            x = rng.uniform(0.0, self.Lx, batch).astype(np.float32)
            y = rng.uniform(0.0, self.Ly, batch).astype(np.float32)
            z = rng.uniform(0.0, self.Lz, batch).astype(np.float32)
            ok = self.mask(x, y, z)
            for p in zip(x[ok], y[ok], z[ok]):
                pts.append(p)
                if len(pts) == n:
                    break
        pts = np.asarray(pts[:n], dtype=np.float32)
        return pts[:, 0], pts[:, 1], pts[:, 2]

    @staticmethod
    def _sample_box_volume(box, n: int, rng):
        x0, x1, y0, y1, z0, z1 = box
        x = rng.uniform(x0, x1, n)
        y = rng.uniform(y0, y1, n)
        z = rng.uniform(z0, z1, n)
        return np.stack([x, y, z], axis=1).astype(np.float32)

    def _sample_support_volume(self, n: int, rng) -> np.ndarray:
        if n <= 0:
            return np.empty((0, 3), dtype=np.float32)
        counts = np.full(len(self.support_boxes), n // len(self.support_boxes), dtype=int)
        counts[: n % len(self.support_boxes)] += 1
        pts = [
            self._sample_box_volume(box, int(count), rng)
            for box, count in zip(self.support_boxes, counts)
            if count > 0
        ]
        return np.concatenate(pts, axis=0).astype(np.float32)

    def _sample_cavity_shell(self, n: int, rng) -> np.ndarray:
        if n <= 0:
            return np.empty((0, 3), dtype=np.float32)
        pts = []
        attempts = 0
        eps_min = 2e-4 * max(self.Lx, self.Ly, self.Lz)
        eps_max = 0.035
        while len(pts) < n and attempts < n * 300:
            attempts += 1
            cav = self.cavity_boxes[int(rng.integers(0, len(self.cavity_boxes)))]
            x, y, z, normal = self._cavity_surface_point(cav, rng)
            nx, ny, nz = normal
            offset = rng.uniform(eps_min, eps_max)
            # The cavity normal points from the material into the void; step
            # against it to place training points inside the surrounding solid.
            p = (x - offset * nx, y - offset * ny, z - offset * nz)
            if self.mask(np.array([p[0]]), np.array([p[1]]), np.array([p[2]]))[0]:
                pts.append(p)
        if len(pts) < n:
            xi, yi, zi = self.sample_interior(n - len(pts), rng=rng)
            pts.extend(zip(xi, yi, zi))
        return np.asarray(pts[:n], dtype=np.float32)

    def sample_training_interior(self, n: int, rng=None, support_frac: float = 0.22, cavity_frac: float = 0.22):
        """
        Feature-balanced interior samples for PINN training.

        Uniform rejection sampling under-represents the small support pads and
        cavity neighborhoods. This helper is intentionally separate from
        sample_interior() so validation/final evaluation remains volume-uniform.
        """
        rng = rng or np.random.default_rng(0)
        n_support = int(round(n * support_frac))
        n_cavity = int(round(n * cavity_frac))
        n_uniform = max(0, n - n_support - n_cavity)

        xi, yi, zi = self.sample_interior(n_uniform, rng=rng)
        parts = [np.stack([xi, yi, zi], axis=1).astype(np.float32)]
        parts.append(self._sample_support_volume(n_support, rng))
        parts.append(self._sample_cavity_shell(n_cavity, rng))
        pts = np.concatenate(parts, axis=0).astype(np.float32)
        rng.shuffle(pts, axis=0)
        return pts[:n, 0], pts[:n, 1], pts[:n, 2]

    @staticmethod
    def _box_surface_point(box, rng):
        x0, x1, y0, y1, z0, z1 = box
        areas = np.array([
            (y1 - y0) * (z1 - z0),
            (y1 - y0) * (z1 - z0),
            (x1 - x0) * (z1 - z0),
            (x1 - x0) * (z1 - z0),
            (x1 - x0) * (y1 - y0),
            (x1 - x0) * (y1 - y0),
        ], dtype=float)
        face = int(rng.choice(6, p=areas / areas.sum()))
        x = rng.uniform(x0, x1)
        y = rng.uniform(y0, y1)
        z = rng.uniform(z0, z1)
        normals = [(-1, 0, 0), (+1, 0, 0), (0, -1, 0), (0, +1, 0), (0, 0, -1), (0, 0, +1)]
        if face == 0:
            x = x0
        elif face == 1:
            x = x1
        elif face == 2:
            y = y0
        elif face == 3:
            y = y1
        elif face == 4:
            z = z0
        else:
            z = z1
        return x, y, z, normals[face]

    @staticmethod
    def _cavity_surface_point(box, rng):
        x, y, z, n = SubframeLike3D._box_surface_point(box, rng)
        return x, y, z, tuple(-float(v) for v in n)

    @staticmethod
    def _cylinder_surface_point(cyl, rng):
        cx, cy, r, z0, z1 = cyl
        lateral_area = 2.0 * np.pi * r * (z1 - z0)
        cap_area = np.pi * r ** 2
        choice = rng.choice(3, p=np.array([lateral_area, cap_area, cap_area]) / (lateral_area + 2 * cap_area))
        phi = rng.uniform(0.0, 2.0 * np.pi)
        if choice == 0:
            x = cx + r * np.cos(phi)
            y = cy + r * np.sin(phi)
            z = rng.uniform(z0, z1)
            n = (np.cos(phi), np.sin(phi), 0.0)
        else:
            rr = r * np.sqrt(rng.uniform(0.0, 1.0))
            x = cx + rr * np.cos(phi)
            y = cy + rr * np.sin(phi)
            z = z0 if choice == 1 else z1
            n = (0.0, 0.0, -1.0 if choice == 1 else +1.0)
        return x, y, z, n

    def sample_boundary(self, n: int, rng=None):
        rng = rng or np.random.default_rng(1)
        pts, normals = [], []
        sources = (
            [("box", b) for b in self._all_boxes]
            + [("cyl", c) for c in self.cylinders]
            + [("cavity", c) for c in self.cavity_boxes]
        )
        eps = 2e-4 * max(self.Lx, self.Ly, self.Lz)
        attempts = 0
        while len(pts) < n and attempts < n * 800:
            attempts += 1
            kind, obj = sources[int(rng.integers(0, len(sources)))]
            if kind == "box":
                x, y, z, normal = self._box_surface_point(obj, rng)
            elif kind == "cyl":
                x, y, z, normal = self._cylinder_surface_point(obj, rng)
            else:
                x, y, z, normal = self._cavity_surface_point(obj, rng)
            nx, ny, nz = normal
            inside = self.mask(
                np.array([x - eps * nx]), np.array([y - eps * ny]), np.array([z - eps * nz])
            )[0]
            outside = self.mask(
                np.array([x + eps * nx]), np.array([y + eps * ny]), np.array([z + eps * nz])
            )[0]
            if inside and not outside:
                pts.append((x, y, z))
                normals.append((nx, ny, nz))

        if len(pts) < n:
            # Conservative fallback: bottom contact-pad points.
            while len(pts) < n:
                box = self.support_boxes[int(rng.integers(0, len(self.support_boxes)))]
                x0, x1, y0, y1, z0, _ = box
                pts.append((rng.uniform(x0, x1), rng.uniform(y0, y1), z0))
                normals.append((0.0, 0.0, -1.0))

        pts = np.asarray(pts[:n], dtype=np.float32)
        normals = np.asarray(normals[:n], dtype=np.float32)
        return pts[:, 0], pts[:, 1], pts[:, 2], normals[:, 0], normals[:, 1], normals[:, 2]

    @staticmethod
    def _box_boundary_distance(coords, box):
        x0, x1, y0, y1, z0, z1 = box
        x, y, z = coords[:, 0], coords[:, 1], coords[:, 2]
        inside = SubframeLike3D._inside_box(x, y, z, box)
        d = np.full(coords.shape[0], np.inf, dtype=np.float32)
        if np.any(inside):
            d[inside] = np.minimum.reduce([
                x[inside] - x0, x1 - x[inside],
                y[inside] - y0, y1 - y[inside],
                z[inside] - z0, z1 - z[inside],
            ]).astype(np.float32)
        return d

    @staticmethod
    def _cyl_boundary_distance(coords, cyl):
        cx, cy, r0, z0, z1 = cyl
        x, y, z = coords[:, 0], coords[:, 1], coords[:, 2]
        r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        inside = (r <= r0) & (z >= z0) & (z <= z1)
        d = np.full(coords.shape[0], np.inf, dtype=np.float32)
        if np.any(inside):
            d[inside] = np.minimum.reduce([r0 - r[inside], z[inside] - z0, z1 - z[inside]]).astype(np.float32)
        return d

    @staticmethod
    def _distance_to_box_surface(coords, box):
        x0, x1, y0, y1, z0, z1 = box
        x, y, z = coords[:, 0], coords[:, 1], coords[:, 2]
        dx = np.maximum.reduce([x0 - x, x - x1, np.zeros_like(x)])
        dy = np.maximum.reduce([y0 - y, y - y1, np.zeros_like(y)])
        dz = np.maximum.reduce([z0 - z, z - z1, np.zeros_like(z)])
        outside = np.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
        inside = SubframeLike3D._inside_box(x, y, z, box)
        if np.any(inside):
            inside_d = np.minimum.reduce([x[inside] - x0, x1 - x[inside], y[inside] - y0, y1 - y[inside], z[inside] - z0, z1 - z[inside]])
            outside[inside] = inside_d
        return outside.astype(np.float32)

    def surface_distance(self, coords_np: np.ndarray) -> tuple[np.ndarray, float]:
        coords = np.asarray(coords_np, dtype=np.float32)
        d = np.full(coords.shape[0], np.inf, dtype=np.float32)
        for box in self._all_boxes:
            d = np.minimum(d, self._box_boundary_distance(coords, box))
        for cyl in self.cylinders:
            d = np.minimum(d, self._cyl_boundary_distance(coords, cyl))
        for cav in self.cavity_boxes:
            d = np.minimum(d, self._distance_to_box_surface(coords, cav))
        d[~np.isfinite(d)] = 0.0
        return np.maximum(d, 0.0).astype(np.float32), 0.06

    def _surface_factor(self, coords_np: np.ndarray) -> np.ndarray:
        coords = np.asarray(coords_np, dtype=np.float32)
        d_ext = np.full(coords.shape[0], np.inf, dtype=np.float32)
        for box in self.boxes:
            d_ext = np.minimum(d_ext, self._box_boundary_distance(coords, box))
        for cyl in self.cylinders:
            d_ext = np.minimum(d_ext, self._cyl_boundary_distance(coords, cyl))
        d_support = np.full(coords.shape[0], np.inf, dtype=np.float32)
        for box in self.support_boxes:
            d_support = np.minimum(d_support, self._box_boundary_distance(coords, box))
        d_cavity = np.full(coords.shape[0], np.inf, dtype=np.float32)
        for cav in self.cavity_boxes:
            d_cavity = np.minimum(d_cavity, self._distance_to_box_surface(coords, cav))

        stacked = np.vstack([d_ext, d_support, d_cavity])
        nearest = np.argmin(stacked, axis=0)
        factors = np.choose(nearest, [1.0, 0.35, 0.45]).astype(np.float32)
        return factors

    def end_prior_cooling_factor(self, coords_np: np.ndarray, args) -> np.ndarray:
        distance, length = self.surface_distance(coords_np)
        length = max(float(length) * args.surface_prior_length_scale, 1e-9)
        proximity = np.exp(-distance / length)
        raw = args.surface_prior_min_factor + args.surface_prior_strength * proximity * self._surface_factor(coords_np)
        raw_mean = float(np.mean(raw))
        if raw_mean > 1e-9:
            raw = raw / raw_mean
        return raw.astype(np.float32)

    def theta(self, x, y, z, t):
        coords = np.stack(np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(y, dtype=float), np.asarray(z, dtype=float)), axis=-1).reshape(-1, 3)
        d, length = self.surface_distance(coords.astype(np.float32))
        factor = self._surface_factor(coords.astype(np.float32))
        t_arr = np.asarray(t, dtype=float)
        t_flat = np.broadcast_to(t_arr, coords.shape[0]).reshape(-1) if t_arr.ndim == 0 else np.asarray(t_arr, dtype=float).reshape(-1)
        if t_flat.size == 1:
            t_flat = np.full(coords.shape[0], float(t_flat[0]))
        proximity = np.exp(-d / max(length, 1e-9))
        gamma = 0.009 + 0.041 * factor * proximity
        boss_boost = np.zeros(coords.shape[0], dtype=np.float32)
        for cx, cy, r0, z0, z1 in self.cylinders:
            rr = np.sqrt((coords[:, 0] - cx) ** 2 + (coords[:, 1] - cy) ** 2)
            boss_boost += 0.12 * np.exp(-(rr / max(r0, 1e-9)) ** 2) * ((coords[:, 2] >= z0) & (coords[:, 2] <= z1))
        theta = np.exp(-gamma * t_flat) * (1.0 + boss_boost * (1.0 - np.exp(-0.06 * t_flat)))
        theta = np.clip(theta, 0.0, 1.0)
        return theta.reshape(np.broadcast_arrays(np.asarray(x), np.asarray(y), np.asarray(z))[0].shape)

    def T(self, x, y, z, t):
        return T_WATER + DELTA_T * self.theta(x, y, z, t)

    def area_volume_ratio(self):
        return 30.0

    def info(self):
        return (
            f"SubframeLike3D  bbox={self.Lx}×{self.Ly}×{self.Lz} m  "
            f"boxes={len(self._all_boxes)} cylinders={len(self.cylinders)} "
            f"cavities={len(self.cavity_boxes)}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Domain registry and factory
# ══════════════════════════════════════════════════════════════════════════════

DOMAINS_3D: dict[str, type] = {
    "rectangular": Rectangular3D,
    "cylinder":    Cylinder3D,
    "stacked":     StackedCubes3D,
    "lshape":      LShape3D,
    "subframe_like": SubframeLike3D,
}

# Default constructor kwargs matching the Level 8 experiments (Mortensen et al., 2026)
_DOMAIN_DEFAULTS: dict[str, dict] = {
    "rectangular": dict(Lx=1.3, Ly=0.6, Lz=0.4),
    "cylinder":    dict(R=0.15, Hz=0.4),
    "stacked":     dict(L_cube=0.5, N_stack=2),
    "lshape":      dict(Lx=0.8, Ly=0.8, Lz=0.4, cut_x=0.3, cut_y=0.3),
    "subframe_like": dict(Lx=1.3, Ly=0.65, Lz=0.32),
}


def make_domain_3d(name: str, **kwargs):
    """
    Instantiate a 3D domain by name with optional parameter overrides.

    Example
    -------
        domain = make_domain_3d("cylinder", R=0.10, Hz=0.30)
        domain = make_domain_3d("rectangular")   # uses defaults from paper
    """
    if name not in DOMAINS_3D:
        raise ValueError(f"Unknown 3D domain '{name}'. "
                         f"Choose from: {list(DOMAINS_3D)}")
    cls  = DOMAINS_3D[name]
    kw   = dict(_DOMAIN_DEFAULTS.get(name, {}))
    kw.update(kwargs)
    return cls(**kw)
