"""
thermal_pinn/physics/fem_reference.py
======================================
make_reference_domain() — train_all.py'nin beklediği fabrika fonksiyonu.

FEM h(T) snapshot datasını yükler ve trainer.py ile uyumlu bir domain
nesnesi döndürür.  Analytical domain.T() yerine FEM interpolasyonu kullanır.
"""

from pathlib import Path
from thermal_pinn.physics.fem.fem_reference import FEMReference

# Domain parametreleri (Lx, Ly veya R)
_DOMAIN_PARAMS_2D = {
    "rectangle": {"Lx": 1.3, "Ly": 0.6, "x_min": 0.0, "y_min": 0.0, "geometry": "rectangle"},
    "circle":    {"Lx": 0.6, "Ly": 0.6, "x_min":-0.3, "y_min":-0.3, "geometry": "circle",    "R": 0.3},
    "annulus":   {"Lx": 0.6, "Ly": 0.6, "x_min":-0.3, "y_min":-0.3, "geometry": "circle",    "R": 0.3},
    "lshape":    {"Lx": 2.0, "Ly": 2.0, "x_min": 0.0, "y_min": 0.0, "geometry": "lshape"},
}

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def make_reference_domain(domain_name: str, dim: int = 2):
    """
    Parameters
    ----------
    domain_name : str  e.g. "rectangle", "circle", "lshape"
    dim         : int  2 (3D desteği sonraki aşamada eklenecek)

    Returns
    -------
    FEMReference nesne — .T(), .sample_interior(), .sample_boundary() destekli
    """
    if dim != 2:
        raise NotImplementedError("3D FEM reference henuz desteklenmiyor.")

    npz = _DATA_DIR / f"fem_hT_{domain_name}.npz"
    if not npz.exists():
        raise FileNotFoundError(
            f"FEM veri dosyasi bulunamadi: {npz}\n"
            f"Once: python3 thermal_pinn/physics/fem/generate_fem_data.py"
        )

    params = _DOMAIN_PARAMS_2D.get(domain_name, {"Lx": 1.0, "Ly": 1.0})
    return FEMReference(npz, **params)
