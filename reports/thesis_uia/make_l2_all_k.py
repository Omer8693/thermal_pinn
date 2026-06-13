"""
Regenerate l2_all_k_*.png figures — per-window L2 relative error vs simulation time.
Each line = 10-seed mean; shaded band = ±1 std across seeds.
Run from repo root:  python thermal_pinn/reports/thesis_uia/make_l2_all_k.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import json
import numpy as np
from pathlib import Path

CKPT_MAIN     = Path("thermal_pinn/checkpoints")
CKPT_IMPROVED = Path("thermal_pinn/checkpoints/improved3d")
CKPT_FIN      = Path("thermal_pinn/checkpoints/thermal_fin")
OUT           = Path("thermal_pinn/reports/thesis_uia/Figures/seed_results")

K_VALS      = [1, 2, 3, 4, 5]
FEM_SAVINGS = {1: "0%", 2: "50%", 3: "65%", 4: "75%", 5: "80%"}
K_COLORS    = {1: "#0f4c81", 2: "#2196F3", 3: "#00897B", 4: "#F57F17", 5: "#C62828"}

ARCHS       = ["bayesian", "nsga2", "nsga3"]
ARCH_LABELS = {"bayesian": "Bayesian/TPE", "nsga2": "NSGA-II", "nsga3": "NSGA-III"}

_IMPROVED3D = {"seed_D", "seed_E", "seed_F", "seed_G", "seed_H", "seed_I", "seed_J"}


# ── Seed path resolvers ───────────────────────────────────────────────────────

def _paths_canonical(domain, arch, k, dim):
    tags = ["", "seed_B", "seed_C", "seed_D", "seed_E",
            "seed_F", "seed_G", "seed_H", "seed_I", "seed_J"]
    paths = []
    for tag in tags:
        if dim == 3 and tag in _IMPROVED3D:
            p = CKPT_IMPROVED / f"{domain}_{arch}_k{k}_dim{dim}_{tag}_metrics.json"
        else:
            tag_part = f"_{tag}" if tag else ""
            p = CKPT_MAIN / f"{domain}_{arch}{tag_part}_k{k}_dim{dim}_metrics.json"
        paths.append(p)
    return paths


def _paths_thermal_fin(arch, k):
    if arch == "bayesian":
        tags = ["fourier", "seed_B_fourier", "seed_C_fourier",
                "seed_D", "seed_E", "seed_F", "seed_G", "seed_H", "seed_I", "seed_J"]
    else:
        tags = ["fin3d", "seed_B", "seed_C", "seed_D", "seed_E",
                "seed_F", "seed_G", "seed_H", "seed_I", "seed_J"]
    return [CKPT_FIN / f"thermal_fin_{arch}_k{k}_{tag}_metrics.json" for tag in tags]


def _load_all_seeds(paths):
    """Return list of windows lists, one per available seed."""
    results = []
    for p in paths:
        if p.exists():
            try:
                m = json.loads(p.read_text())
                if "windows" in m and m["windows"]:
                    results.append(m["windows"])
            except Exception:
                pass
    return results


def _aggregate_windows(seeds_wins):
    """
    Given a list of windows-lists (one per seed), return:
      t_x   — shared time axis (t_end values from the shortest seed)
      means  — mean L2 per window across seeds
      stds   — std L2 per window across seeds
    """
    if not seeds_wins:
        return None, None, None
    n_wins = min(len(ws) for ws in seeds_wins)
    t_x   = [seeds_wins[0][i]["t_end"] for i in range(n_wins)]
    l2_matrix = np.array([[ws[i]["l2_rel"] for i in range(n_wins)] for ws in seeds_wins])
    means = l2_matrix.mean(axis=0)
    stds  = l2_matrix.std(axis=0, ddof=1) if len(seeds_wins) > 1 else np.zeros(n_wins)
    return t_x, means, stds


# ── Grid plotter ──────────────────────────────────────────────────────────────

def _plot_l2_grid(domains, dim, title_prefix, out_name, path_fn):
    n_dom      = len(domains)
    n_arch     = len(ARCHS)
    one_domain = n_dom == 1
    n_rows = 1 if one_domain else n_arch
    n_cols = n_arch if one_domain else n_dom

    fig, axes = plt.subplots(
        n_rows, n_cols,
        figsize=(4.8 * n_cols, 3.2 * n_rows),
        sharex=False, sharey=False,
        squeeze=False,
    )
    fig.patch.set_facecolor("white")
    fig.suptitle(
        f"{title_prefix} — Per-window L₂ relative error (10-seed mean ±1σ)",
        fontsize=12, fontweight="bold", y=1.01, color="#0f172a",
    )

    for row, arch in enumerate(ARCHS):
        for col, domain in enumerate(domains):
            ax = axes[0][row] if one_domain else axes[row][col]
            ax.set_facecolor("white")
            for sp in ax.spines.values():
                sp.set_linewidth(0.7)
                sp.set_color("#94a3b8")

            any_data = False
            for k in K_VALS:
                paths      = path_fn(domain, arch, k, dim)
                seeds_wins = _load_all_seeds(paths)
                t_x, means, stds = _aggregate_windows(seeds_wins)
                if t_x is None:
                    continue

                c = K_COLORS[k]
                ax.plot(t_x, means,
                        color=c, lw=1.8, linestyle="solid",
                        marker="o", ms=3.0,
                        markerfacecolor=c, markeredgewidth=0,
                        zorder=4, label=f"k={k} ({FEM_SAVINGS[k]})")
                ax.fill_between(t_x,
                                means - stds,
                                means + stds,
                                color=c, alpha=0.15, zorder=2)
                any_data = True

            ax.set_xlim(left=0, right=30)
            ax.yaxis.grid(True, linestyle="--", alpha=0.3, zorder=0)
            ax.set_axisbelow(True)
            ax.set_xlabel("Simulation time [s]", fontsize=8)
            ax.set_ylabel("L₂ relative error", fontsize=8)
            ax.tick_params(labelsize=7.5)

            if not any_data:
                ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                        ha="center", va="center", color="gray", fontsize=9)

            dom_label = domain.replace("_", " ").capitalize()
            ax.set_title(f"{dom_label} — {ARCH_LABELS[arch]}",
                         fontsize=9, fontweight="normal", pad=4, color="#1e293b")

    legend_handles = [
        mlines.Line2D([], [], color=K_COLORS[k], lw=2.0,
                      linestyle="solid", label=f"k={k} ({FEM_SAVINGS[k]})")
        for k in K_VALS
    ]
    fig.legend(handles=legend_handles,
               loc="lower center", ncol=5, fontsize=9,
               framealpha=0.95, edgecolor="#cbd5e1",
               bbox_to_anchor=(0.5, -0.03))

    fig.tight_layout(rect=[0, 0.05, 1, 1])
    out_path = OUT / out_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"Saved → {out_path}")


# ── Path function wrappers ────────────────────────────────────────────────────

def _canonical_fn(domain, arch, k, dim):
    return _paths_canonical(domain, arch, k, dim)


def _thermal_fin_fn(domain, arch, k, dim):
    return _paths_thermal_fin(arch, k)


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)

    _plot_l2_grid(["rectangle", "circle", "lshape"], 2,
                  "2D Benchmark", "l2_all_k_2d.png", _canonical_fn)

    _plot_l2_grid(["rectangular", "cylinder", "stacked", "lshape"], 3,
                  "3D Benchmark", "l2_all_k_3d.png", _canonical_fn)

    _plot_l2_grid(["thermal_fin"], 3,
                  "Thermal Fin", "l2_all_k_thermal_fin.png", _thermal_fin_fn)
