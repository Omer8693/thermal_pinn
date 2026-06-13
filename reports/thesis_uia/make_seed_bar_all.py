"""
make_seed_bar_all.py
====================
Generate seed-sensitivity bar charts for 2D, 3D, and Thermal Fin domains.
Each panel shows mean MAE ± 1 std across 10 independent seeds per skip factor.

Run from repo root:
    python thermal_pinn/reports/thesis_uia/make_seed_bar_all.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import json
import numpy as np
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
CKPT_MAIN     = Path("thermal_pinn/checkpoints")
CKPT_IMPROVED = Path("thermal_pinn/checkpoints/improved3d")
CKPT_FIN      = Path("thermal_pinn/checkpoints/thermal_fin")
OUT           = Path("thermal_pinn/reports/thesis_uia/Figures/seed_results")

# ── Constants ─────────────────────────────────────────────────────────────────
K_VALS      = [1, 2, 3, 4, 5]
FEM_PCT     = {1: "0%", 2: "50%", 3: "65%", 4: "75%", 5: "80%"}
ARCHS       = ["bayesian", "nsga2", "nsga3"]
ARCH_LABELS = {"bayesian": "Bayesian/TPE", "nsga2": "NSGA-II", "nsga3": "NSGA-III"}
ARCH_COLORS = {"bayesian": "#1A5C96", "nsga2": "#C62828", "nsga3": "#2E7D32"}
THRESHOLD_2D = 10.0
THRESHOLD_3D = 15.0

# Seeds D-J stored in improved3d/ for canonical 3D
_IMPROVED3D_TAGS = {"seed_D", "seed_E", "seed_F", "seed_G", "seed_H", "seed_I", "seed_J"}

# ── Data loading ───────────────────────────────────────────────────────────────

def _load_json(p: Path):
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None


def load_canonical_mae(domain: str, arch: str, k: int, dim: int) -> list[float]:
    """Load mean_mae for all 10 seeds of a canonical domain."""
    tags = ["", "seed_B", "seed_C", "seed_D", "seed_E",
            "seed_F", "seed_G", "seed_H", "seed_I", "seed_J"]
    maes = []
    for tag in tags:
        if dim == 3 and tag in _IMPROVED3D_TAGS:
            p = CKPT_IMPROVED / f"{domain}_{arch}_k{k}_dim{dim}_{tag}_metrics.json"
        else:
            tag_part = f"_{tag}" if tag else ""
            p = CKPT_MAIN / f"{domain}_{arch}{tag_part}_k{k}_dim{dim}_metrics.json"
        m = _load_json(p)
        if m and "mean_mae" in m:
            maes.append(float(m["mean_mae"]))
    return maes


def load_thermal_fin_mae(arch: str, k: int) -> list[float]:
    """Load mean_mae for all 10 seeds of thermal fin."""
    if arch == "bayesian":
        # Seeds A-C use fourier tags; D-J use plain seed_X tags
        tags = [
            "fourier", "seed_B_fourier", "seed_C_fourier",
            "seed_D", "seed_E", "seed_F", "seed_G", "seed_H", "seed_I", "seed_J",
        ]
    else:
        tags = [
            "fin3d", "seed_B", "seed_C", "seed_D", "seed_E",
            "seed_F", "seed_G", "seed_H", "seed_I", "seed_J",
        ]
    maes = []
    for tag in tags:
        p = CKPT_FIN / f"thermal_fin_{arch}_k{k}_{tag}_metrics.json"
        m = _load_json(p)
        if m and "mean_mae" in m:
            maes.append(float(m["mean_mae"]))
    return maes


# ── Plotting helpers ───────────────────────────────────────────────────────────

def _style_ax(ax, ylabel=True):
    ax.set_facecolor("white")
    ax.yaxis.grid(True, linestyle="--", alpha=0.35, zorder=0, color="#94a3b8")
    ax.set_axisbelow(True)
    for sp in ax.spines.values():
        sp.set_linewidth(0.6)
        sp.set_color("#cbd5e1")
    ax.tick_params(labelsize=7.5, length=3)
    ax.set_xlabel("Skip factor $k$", fontsize=8)
    if ylabel:
        ax.set_ylabel("Mean-window MAE (°C)", fontsize=8)
    ax.set_xticks(K_VALS)
    ax.set_xticklabels([f"k={k}\n({FEM_PCT[k]})" for k in K_VALS], fontsize=7)


def _draw_bars(ax, arch_data: dict, threshold: float):
    """
    arch_data: {arch: {k: (mean, std)}}
    Draw grouped bar chart; one group per k, one bar per arch.
    """
    n_arch = len(ARCHS)
    width  = 0.22
    offsets = np.linspace(-(n_arch - 1) * width / 2,
                          (n_arch - 1) * width / 2, n_arch)

    for i, arch in enumerate(ARCHS):
        xs     = np.array(K_VALS, dtype=float) + offsets[i]
        means  = [arch_data[arch].get(k, (np.nan, np.nan))[0] for k in K_VALS]
        stds   = [arch_data[arch].get(k, (np.nan, np.nan))[1] for k in K_VALS]
        colors = [ARCH_COLORS[arch]] * len(K_VALS)
        ax.bar(xs, means, width=width, color=colors, alpha=0.82,
               zorder=3, label=ARCH_LABELS[arch])
        ax.errorbar(xs, means, yerr=stds, fmt="none",
                    ecolor="#1e293b", elinewidth=1.2, capsize=3, zorder=4)

    ax.axhline(threshold, color="#dc2626", linestyle="--",
               lw=1.2, zorder=5, label=f"{int(threshold)}°C threshold")
    ax.set_xticks(K_VALS)
    ax.set_xticklabels([f"k={k}\n({FEM_PCT[k]})" for k in K_VALS], fontsize=7)


def _draw_line(ax, arch_data: dict, threshold: float):
    """Line + shaded band version (mean ± std) — one line per arch."""
    for arch in ARCHS:
        xs    = K_VALS
        means = [arch_data[arch].get(k, (np.nan, np.nan))[0] for k in K_VALS]
        stds  = [arch_data[arch].get(k, (np.nan, np.nan))[1] for k in K_VALS]
        means = np.array(means, dtype=float)
        stds  = np.array(stds,  dtype=float)
        ax.plot(xs, means, color=ARCH_COLORS[arch], lw=2.0,
                marker="o", ms=5, zorder=3, label=ARCH_LABELS[arch])
        ax.fill_between(xs, means - stds, means + stds,
                        color=ARCH_COLORS[arch], alpha=0.15, zorder=2)

    ax.axhline(threshold, color="#dc2626", linestyle="--",
               lw=1.2, zorder=5, label=f"{int(threshold)}°C threshold")
    ax.set_xticks(K_VALS)
    ax.set_xticklabels([f"k={k}\n({FEM_PCT[k]})" for k in K_VALS], fontsize=7)


# ── 2D seed bar ───────────────────────────────────────────────────────────────

def make_seed_bar_2d():
    domains_2d = ["rectangle", "circle", "lshape"]
    domain_labels = {"rectangle": "Rectangle", "circle": "Circle", "lshape": "L-shape"}

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 3.8), sharey=False)
    fig.patch.set_facecolor("white")
    fig.suptitle(
        "Seed-to-Seed Variability — 2D Benchmark (Ten Seeds, Mean ± 1 Std)",
        fontsize=11, fontweight="bold", color="#0f172a", y=1.01,
    )

    for ax, domain in zip(axes, domains_2d):
        arch_data: dict = {}
        for arch in ARCHS:
            arch_data[arch] = {}
            for k in K_VALS:
                vals = load_canonical_mae(domain, arch, k, dim=2)
                if vals:
                    arch_data[arch][k] = (float(np.mean(vals)), float(np.std(vals, ddof=1) if len(vals) > 1 else 0.0))

        _draw_line(ax, arch_data, THRESHOLD_2D)
        _style_ax(ax, ylabel=(ax is axes[0]))
        ax.set_title(domain_labels[domain], fontsize=10, fontweight="normal",
                     pad=4, color="#1e293b")

    handles = [mpatches.Patch(color=ARCH_COLORS[a], label=ARCH_LABELS[a]) for a in ARCHS]
    handles.append(plt.Line2D([0], [0], color="#dc2626", linestyle="--",
                              lw=1.5, label="10°C threshold"))
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=8.5,
               framealpha=0.95, edgecolor="#cbd5e1", bbox_to_anchor=(0.5, -0.06))

    fig.tight_layout(rect=[0, 0.06, 1, 1])
    out = OUT / "seed_bar_2d.png"
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"Saved → {out}")


# ── 3D seed bar ───────────────────────────────────────────────────────────────

def make_seed_bar_3d():
    domains_3d = ["rectangular", "cylinder", "stacked", "lshape"]
    domain_labels = {
        "rectangular": "Rectangular", "cylinder": "Cylinder",
        "stacked": "Stacked Cubes", "lshape": "L-shape 3D",
    }

    fig, axes = plt.subplots(1, 4, figsize=(17, 3.8), sharey=False)
    fig.patch.set_facecolor("white")
    fig.suptitle(
        "Seed-to-Seed Variability — 3D Benchmark (Ten Seeds, Mean ± 1 Std)",
        fontsize=11, fontweight="bold", color="#0f172a", y=1.01,
    )

    for ax, domain in zip(axes, domains_3d):
        arch_data: dict = {}
        for arch in ARCHS:
            arch_data[arch] = {}
            for k in K_VALS:
                vals = load_canonical_mae(domain, arch, k, dim=3)
                if vals:
                    arch_data[arch][k] = (float(np.mean(vals)), float(np.std(vals, ddof=1) if len(vals) > 1 else 0.0))

        _draw_line(ax, arch_data, THRESHOLD_3D)
        _style_ax(ax, ylabel=(ax is axes[0]))
        ax.set_title(domain_labels[domain], fontsize=10, fontweight="normal",
                     pad=4, color="#1e293b")

    handles = [mpatches.Patch(color=ARCH_COLORS[a], label=ARCH_LABELS[a]) for a in ARCHS]
    handles.append(plt.Line2D([0], [0], color="#dc2626", linestyle="--",
                              lw=1.5, label="15°C threshold"))
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=8.5,
               framealpha=0.95, edgecolor="#cbd5e1", bbox_to_anchor=(0.5, -0.06))

    fig.tight_layout(rect=[0, 0.06, 1, 1])
    out = OUT / "seed_bar_3d.png"
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"Saved → {out}")


# ── Thermal Fin seed bar ───────────────────────────────────────────────────────

def make_seed_bar_thermal_fin():
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 3.8), sharey=True)
    fig.patch.set_facecolor("white")
    fig.suptitle(
        "Seed-to-Seed Variability — Thermal Fin (Ten Seeds, Mean ± 1 Std)",
        fontsize=11, fontweight="bold", color="#0f172a", y=1.01,
    )

    for ax, arch in zip(axes, ARCHS):
        means_k, stds_k = [], []
        for k in K_VALS:
            vals = load_thermal_fin_mae(arch, k)
            if vals:
                means_k.append(float(np.mean(vals)))
                stds_k.append(float(np.std(vals, ddof=1) if len(vals) > 1 else 0.0))
            else:
                means_k.append(np.nan)
                stds_k.append(np.nan)

        means_k = np.array(means_k)
        stds_k  = np.array(stds_k)

        ax.plot(K_VALS, means_k, color=ARCH_COLORS[arch], lw=2.2,
                marker="o", ms=6, zorder=3)
        ax.fill_between(K_VALS, means_k - stds_k, means_k + stds_k,
                        color=ARCH_COLORS[arch], alpha=0.18, zorder=2)

        # Individual seed scatter (light dots)
        for i, k in enumerate(K_VALS):
            vals = load_thermal_fin_mae(arch, k)
            if vals:
                ax.scatter([k] * len(vals), vals,
                           color=ARCH_COLORS[arch], alpha=0.25, s=14, zorder=1)

        ax.axhline(THRESHOLD_3D, color="#dc2626", linestyle="--",
                   lw=1.2, zorder=5, label="15°C threshold")

        _style_ax(ax, ylabel=(ax is axes[0]))
        ax.set_title(ARCH_LABELS[arch], fontsize=10, fontweight="normal",
                     pad=4, color="#1e293b")
        ax.set_facecolor("white")
        ax.yaxis.grid(True, linestyle="--", alpha=0.35, zorder=0, color="#94a3b8")
        ax.set_axisbelow(True)
        for sp in ax.spines.values():
            sp.set_linewidth(0.6)
            sp.set_color("#cbd5e1")
        ax.tick_params(labelsize=7.5, length=3)

    axes[-1].legend(fontsize=8, loc="upper left",
                    framealpha=0.9, edgecolor="#cbd5e1")

    fig.tight_layout(rect=[0, 0.02, 1, 1])
    out = OUT / "seed_bar_thermal_fin.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"Saved → {out}")


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    make_seed_bar_2d()
    make_seed_bar_3d()
    make_seed_bar_thermal_fin()
    print("Done.")
