"""
Per-window MAE diagnostic figures for 3D benchmark domains.
Generates one PNG per (arch, domain) at k=1 — 12 figures total.

Run from this directory:
    python make_3d_diag.py
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

BASE = Path("../../checkpoints")
OUT  = Path("Figures")
OUT.mkdir(parents=True, exist_ok=True)

DOMAINS = ["rectangular", "cylinder", "stacked", "lshape"]
DLABELS = {
    "rectangular": "Rectangular Prism",
    "cylinder":    "Cylinder",
    "stacked":     "Stacked Cubes",
    "lshape":      "L-shape Prism",
}

ARCHS = ["bayesian", "nsga2", "nsga3"]
ALABELS = {
    "bayesian": "Bayesian/TPE",
    "nsga2":    "NSGA-II",
    "nsga3":    "NSGA-III",
}
ACOLORS = {
    "bayesian": "#1A5C96",
    "nsga2":    "#C62828",
    "nsga3":    "#2E7D32",
}

_FIG_BG = "#f7f1e3"
_AX_BG  = "#fffdf8"


def load_windows(domain: str, arch: str) -> list[dict]:
    path = BASE / f"{domain}_{arch}_k1_dim3_metrics.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data.get("windows", [])


def make_diag(domain: str, arch: str) -> None:
    windows = load_windows(domain, arch)
    if not windows:
        print(f"  [skip] {domain} / {arch} — no data")
        return

    t_mid = [0.5 * (w["t_start"] + w["t_end"]) for w in windows]
    mae   = [w["mae_C"] for w in windows]
    win_idx = list(range(1, len(windows) + 1))

    fig, ax = plt.subplots(figsize=(4.8, 3.4))
    fig.patch.set_facecolor(_FIG_BG)
    ax.set_facecolor(_AX_BG)
    for spine in ax.spines.values():
        spine.set_edgecolor("#d8cfbf")

    ax.plot(win_idx, mae,
            color=ACOLORS[arch], lw=2.0, marker="o", ms=5,
            markerfacecolor="white", markeredgewidth=1.4,
            label=ALABELS[arch], zorder=3)

    mean_mae = float(np.mean(mae))
    ax.axhline(mean_mae, color=ACOLORS[arch], lw=1.2,
               linestyle="--", alpha=0.7,
               label=f"Mean {mean_mae:.1f}°C")

    ax.set_title(f"{ALABELS[arch]} — {DLABELS[domain]}",
                 fontsize=10, fontweight="bold", color="#2f2a24")
    ax.set_xlabel("Window index", fontsize=9, color="#4c463f")
    ax.set_ylabel("MAE [°C]", fontsize=9, color="#4c463f")
    ax.set_xticks(win_idx[::4])
    ax.tick_params(colors="#4c463f", labelsize=8)
    ax.grid(True, linestyle="--", alpha=0.35, color="#c0b8a8")
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=8, framealpha=0.7, loc="upper right")

    plt.tight_layout()
    out_path = OUT / f"3d_diag_{arch}_{domain}.png"
    plt.savefig(out_path, dpi=180, bbox_inches="tight", facecolor=_FIG_BG)
    plt.close(fig)
    print(f"  Saved → {out_path}")


if __name__ == "__main__":
    print("Generating 3D diagnostic figures...")
    for domain in DOMAINS:
        for arch in ARCHS:
            make_diag(domain, arch)
    print("Done — 12 figures generated.")
