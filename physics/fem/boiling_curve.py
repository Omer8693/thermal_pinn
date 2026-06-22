"""
h(T) boiling curve for A356 aluminium water quenching.

5 regimes (Mortensen 2026 Fig. 6 — piecewise linear approximation):
  1. Film boiling        T > 450°C   : h ≈ 700  W/m²K  (vapour blanket)
  2. Transition          300–450°C   : h rises  700 → 20000
  3. Nucleate boiling    150–300°C   : h falls  20000 → 8000  (peak ~300°C)
  4. Low nucleate        80–150°C    : h falls  8000 → 3500
  5. Single-phase conv.  T < 80°C    : h ≈ 2500 W/m²K

Reference: Mortensen et al. (2026) Int J Adv Manuf Technol,
           Dolan et al. (2005) Mater Sci Eng A, typical A356/357 quench data.
"""

import numpy as np

# Control points: (T [°C], h [W/m²K])
_POINTS = np.array([
    [  20.0,  2500.0],
    [  80.0,  2500.0],
    [ 150.0,  3500.0],
    [ 300.0, 20000.0],   # nucleate boiling peak
    [ 450.0,   700.0],   # Leidenfrost / min-film-boiling temperature
    [ 540.0,   700.0],   # film boiling (initial temperature)
    [ 650.0,   700.0],   # film boiling (extrapolation)
], dtype=float)

_T_pts = _POINTS[:, 0]
_H_pts = _POINTS[:, 1]


def h_boiling(T):
    """
    h(T) [W/m²K] for A356 water quench.

    Parameters
    ----------
    T : float or array-like, temperature in °C

    Returns
    -------
    h : same shape as T, float64
    """
    T_arr = np.asarray(T, dtype=float)
    return np.interp(T_arr, _T_pts, _H_pts)


# Quick self-test / plot when run directly
if __name__ == "__main__":
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from pathlib import Path

    T_range = np.linspace(20, 600, 1000)
    h_range = h_boiling(T_range)

    fig, ax = plt.subplots(figsize=(8, 4))

    ax.plot(T_range, h_range / 1000, color="#c0392b", lw=2)
    ax.set_xlabel("Surface temperature T [°C]")
    ax.set_ylabel("h(T)  [kW/m²K]")
    ax.set_title("A356 water quench — h(T) boiling curve (5 regimes)")

    # Label regimes
    labels = [
        (50,  "Single-phase"),
        (115, "Low nucleate"),
        (225, "Nucleate\npeak"),
        (375, "Transition"),
        (500, "Film boiling"),
    ]
    for T_lbl, txt in labels:
        ax.annotate(txt, xy=(T_lbl, h_boiling(T_lbl)/1000),
                    xytext=(T_lbl, h_boiling(T_lbl)/1000 + 3),
                    fontsize=8, ha="center",
                    arrowprops=dict(arrowstyle="-", color="gray", lw=0.8))

    ax.axhline(5, color="steelblue", lw=0.8, ls="--", alpha=0.7,
               label="constant h=5000 (old)")
    ax.legend(fontsize=8)

    plt.tight_layout()
    out = Path("thermal_pinn/assets/fem/boiling_curve.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150, facecolor=fig.get_facecolor())
    print(f"Kaydedildi: {out}")

    print("\nh(T) örnek değerler:")
    for T in [20, 80, 150, 300, 400, 450, 540]:
        print(f"  T={T:4.0f}°C  h={h_boiling(T):8.1f} W/m²K")
