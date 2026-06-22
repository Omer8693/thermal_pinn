"""
FEMReference — FEM snapshot verisini arbitrary (x,y,t) noktalarında interpole eder.
domain.T(x, y, t) arayüzüyle uyumlu — trainer.py hiç değişmeden kullanılabilir.
"""

import numpy as np
from pathlib import Path
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator


class FEMReference:
    """
    Parameters
    ----------
    npz_path : str veya Path — generate_fem_data.py çıktısı
    Lx, Ly   : domain boyutları (normalisation için, rectangle/lshape)
    x_min, y_min : koordinat alt sınırları (circle: -R)
    geometry : 'rectangle', 'circle', 'lshape'
    R        : circle yarıçapı (geometry='circle' ise)
    """

    T_WATER = 20.0
    T_INIT  = 540.0

    def __init__(self, npz_path, Lx: float = 1.3, Ly: float = 0.6,
                 x_min: float = 0.0, y_min: float = 0.0,
                 geometry: str = "rectangle", R: float = None):
        data = np.load(npz_path)
        self.coords  = data["coords"].astype(np.float64)   # (N, 2)
        self.T_snaps = data["T_snaps"].astype(np.float64)  # (n_t, N)
        self.t_snaps = data["t_snaps"].astype(np.float64)  # (n_t,)
        self.Lx = Lx
        self.Ly = Ly
        self.x_min = x_min
        self.y_min = y_min
        self.geometry = geometry
        self.R = R  # circle için

        # h=700: film boiling başlangıç değeri — BC loss regularizasyon için
        self.h     = 700.0
        self.alpha = 6.25e-5  # m²/s  A356

        # Hazır interpole nesneleri — her snapshot için
        self._interps = []
        for i in range(len(self.t_snaps)):
            lin = LinearNDInterpolator(self.coords, self.T_snaps[i])
            near = NearestNDInterpolator(self.coords, self.T_snaps[i])
            self._interps.append((lin, near))

    # ------------------------------------------------------------------
    # domain.T(x, y, t) arayüzü
    # ------------------------------------------------------------------
    def T(self, x: np.ndarray, y: np.ndarray, t: float) -> np.ndarray:
        """Sıcaklık alanını FEM snapshot'larından interpole et."""
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        pts = np.stack([x, y], axis=1)

        # Zaman: doğrusal interpolasyon
        t_arr = self.t_snaps
        if t <= t_arr[0]:
            return self._interp_space(0, pts)
        if t >= t_arr[-1]:
            return self._interp_space(-1, pts)

        idx = np.searchsorted(t_arr, t) - 1
        idx = max(0, min(idx, len(t_arr) - 2))
        alpha = (t - t_arr[idx]) / (t_arr[idx + 1] - t_arr[idx])
        T0 = self._interp_space(idx,     pts)
        T1 = self._interp_space(idx + 1, pts)
        return (1 - alpha) * T0 + alpha * T1

    def _interp_space(self, idx: int, pts: np.ndarray) -> np.ndarray:
        lin, near = self._interps[idx]
        T = lin(pts)
        # LinearNDInterpolator: dış noktalar için NaN → nearest ile doldur
        mask = np.isnan(T)
        if mask.any():
            T[mask] = near(pts[mask])
        return T

    # ------------------------------------------------------------------
    # trainer.py'nin beklediği sample_* metodları
    # ------------------------------------------------------------------
    def sample_interior(self, n: int, rng=None) -> tuple:
        if rng is None:
            rng = np.random.default_rng()
        if self.geometry == "circle":
            pts = []
            while len(pts) < n:
                batch = rng.uniform(-self.R, self.R, (n * 4, 2))
                inside = batch[:, 0]**2 + batch[:, 1]**2 < self.R**2 * 0.95
                pts.extend(batch[inside].tolist())
            arr = np.array(pts[:n], dtype=np.float32)
            return arr[:, 0], arr[:, 1]
        elif self.geometry == "lshape":
            pts = []
            L = self.Lx
            while len(pts) < n:
                batch = rng.uniform(0, L, (n * 4, 2))
                inside = ~((batch[:, 0] > L/2) & (batch[:, 1] > L/2))
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
            nx, ny = np.cos(theta), np.sin(theta)
            return bx, by, nx, ny
        else:  # rectangle / lshape
            n_per_edge = n // 4
            x0, y0 = self.x_min, self.y_min
            Lx, Ly = self.Lx, self.Ly
            parts = [
                (np.full(n_per_edge, x0),        rng.uniform(y0, y0+Ly, n_per_edge), -np.ones(n_per_edge),  np.zeros(n_per_edge)),
                (np.full(n_per_edge, x0+Lx),     rng.uniform(y0, y0+Ly, n_per_edge), +np.ones(n_per_edge),  np.zeros(n_per_edge)),
                (rng.uniform(x0, x0+Lx, n_per_edge), np.full(n_per_edge, y0),         np.zeros(n_per_edge), -np.ones(n_per_edge)),
                (rng.uniform(x0, x0+Lx, n_per_edge), np.full(n_per_edge, y0+Ly),      np.zeros(n_per_edge), +np.ones(n_per_edge)),
            ]
            bx = np.concatenate([p[0] for p in parts]).astype(np.float32)
            by = np.concatenate([p[1] for p in parts]).astype(np.float32)
            nx = np.concatenate([p[2] for p in parts]).astype(np.float32)
            ny = np.concatenate([p[3] for p in parts]).astype(np.float32)
            return bx, by, nx, ny
