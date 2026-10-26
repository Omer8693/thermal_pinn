"""
experiments/tm_adaptive_k_rectangle_fenics/make_field_comparison.py
=====================================================================
Turns results/field_snapshots.npz (produced by field_snapshots.py) into
three figures using REAL PINN prediction fields (not fallback placeholders
like fenics_repro/results/*_reference_adaptive.png, where no prediction
file was ever supplied and the "prediction" panel is just a copy of the
reference field):

1. results/rectangle_field_comparison.png
   Spatial snapshots at 3 times spanning the 540C -> 20C cooldown
   (t=1.5s, 15.0s, 30.0s - both controllers land exactly on these window
   boundaries, no interpolation needed). Columns: FEM reference | PINN
   prediction | PINN |error| | PINN+TM prediction | PINN+TM |error|.
   Fields are drawn as filled Delaunay-triangulation contours (tricontourf)
   instead of raw scatter dots - 2500 random evaluation points still
   define the mesh, but the plot reads as a continuous field the way a
   real FEM post-processor (ParaView/matplotlib tricontourf) renders one,
   instead of visible individual markers.

2. results/rectangle_mae_trajectory.png
   MAE(t) for both controllers across the full cooldown, with the 10C
   safety threshold AND a reference line for the original thesis result
   (npz-cached FEM engine h=700, 10-seed mean, see
   checkpoints/rectangle_bayesian_adaptive_seed_*_dim2_metrics.json) -
   a third point of comparison ("triple gösterim") without re-running
   anything, since that aggregate is already on disk. Each marker is
   annotated with its numeric MAE value so the plot is readable without
   cross-referencing the y-axis. Bottom panel: k(t) step trajectory.

3. results/rectangle_loss_curves.png
   Training loss (total / PDE / BC / FEM end-supervision) vs cumulative
   epoch, concatenated across all windows in chronological order, with
   vertical dashed lines at window boundaries (labeled with k). Answers
   "how many epochs, and did the loss actually converge" - previously
   only the FINAL loss value of each window was kept, so this curve did
   not exist without re-training from scratch.

Naming: "PINN" (not "Algorithm 3") for the threshold-controlled baseline
and "PINN+TM" (not "TM-guided") for the Tsetlin-Machine-controlled
variant - more academic/report-appropriate phrasing than the internal
code names, which stay "algorithm3"/"tm_guided" (matches the rest of the
experiment's file and variable names).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent  # code/ -> experiment root
RESULTS_DIR = EXPERIMENT_ROOT / "npz"
FIGURES_DIR = EXPERIMENT_ROOT / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
CKPT_DIR = EXPERIMENT_ROOT.parent.parent / "checkpoints"  # thermal_pinn/checkpoints
ACCEPT_THRESH_C = 10.0
SNAPSHOT_TIMES = [1.5, 15.0, 30.0]

DISPLAY_NAME = {"algorithm3": "PINN", "tm_guided": "PINN+TM", "tm_hybrid": "PINN+TM-hybrid"}
COLOR = {"algorithm3": "tab:blue", "tm_guided": "tab:red", "tm_hybrid": "tab:green"}


def npz_dir(geometry: str) -> Path:
    return RESULTS_DIR / geometry


def figures_dir(geometry: str) -> Path:
    d = FIGURES_DIR / geometry
    d.mkdir(parents=True, exist_ok=True)
    return d


def load(arch: str, geometry: str = "rectangle"):
    suffix = "" if arch == "bayesian" else f"_{arch}"
    d = np.load(npz_dir(geometry) / f"field_snapshots{suffix}.npz")
    return {k: d[k] for k in d.files}


def nearest_idx(t_array: np.ndarray, target: float) -> int:
    return int(np.argmin(np.abs(t_array - target)))


def thesis_reference_mean_mae(arch: str, geometry: str = "rectangle") -> float | None:
    """Mean MAE of the ORIGINAL npz-cached (h=700) Algorithm-3 run for this
    architecture/geometry, already on disk from earlier thesis work - no
    re-run needed. Bayesian has a 10-seed sweep; nsga2/nsga3 only have a
    single (non-seeded) run in the checkpoints directory."""
    seed_files = sorted(CKPT_DIR.glob(f"{geometry}_{arch}_adaptive_seed_*_dim2_metrics.json"))
    import json
    if seed_files:
        vals = [json.loads(f.read_text())["mean_mae"] for f in seed_files]
        return float(np.mean(vals)), len(seed_files)
    candidates = sorted(CKPT_DIR.glob(f"{geometry}_{arch}_adaptive*_metrics.json"))
    if not candidates:
        return None
    return float(json.loads(candidates[0].read_text())["mean_mae"]), 1


def draw_field(ax, coords, field, cmap, vmin, vmax, triang, gamma=None):
    # tripcolor + Gouraud shading (per-node smooth interpolation across each
    # triangle) matches how real FEM post-processors (ParaView etc.) render
    # a nodal field. tricontourf was tried first but produces a "hole"
    # artifact wherever the field has a large, exactly-saturated plateau
    # (the PINN output saturates to exactly T=540 or T=20 over broad
    # regions - float-exact ties make contour-level binning ambiguous
    # there); tripcolor has no level binning step, so it does not hit this.
    if gamma is not None:
        # Error fields are extremely right-skewed (median ~0.3-0.4C but a
        # handful of corner points spike to 100-300C where the Robin BC
        # meets the sharp rectangle corner). A linear vmin/vmax scale spends
        # almost its whole range on those few outliers and renders the
        # entire interior - where the actually-interesting 0-10C error
        # lives - as flat black. PowerNorm(gamma<1) compresses the high end
        # and stretches the low end so that interior structure becomes
        # visible while outliers still saturate to the top color.
        norm = matplotlib.colors.PowerNorm(gamma=gamma, vmin=vmin, vmax=vmax)
        return ax.tripcolor(triang, field, cmap=cmap, norm=norm, shading="gouraud")
    return ax.tripcolor(triang, field, cmap=cmap, vmin=vmin, vmax=vmax, shading="gouraud")


def make_field_figure(d: dict, arch: str, geometry: str = "rectangle") -> Path:
    coords = d["coords"]
    triang = mtri.Triangulation(coords[:, 0], coords[:, 1])
    controllers = [c for c in ("algorithm3", "tm_guided", "tm_hybrid") if f"{c}_t" in d]

    err_vmax = 0.0
    idxs = {}
    for ctrl in controllers:
        t_arr = d[f"{ctrl}_t"]
        for t_target in SNAPSHOT_TIMES:
            i = nearest_idx(t_arr, t_target)
            idxs[(ctrl, t_target)] = i
            err = np.abs(d[f"{ctrl}_T_ref"][i] - d[f"{ctrl}_T_pred"][i])
            err_vmax = max(err_vmax, float(np.percentile(err, 99)))
    err_vmax = max(err_vmax, 1.0)

    n_cols = 1 + 2 * len(controllers)
    fig, axes = plt.subplots(len(SNAPSHOT_TIMES), n_cols, figsize=(4.2 * n_cols, 4.2 * len(SNAPSHOT_TIMES)),
                              constrained_layout=True)
    ctrl_names = " vs ".join(DISPLAY_NAME[c] for c in controllers)
    fig.suptitle(
        f"{geometry.capitalize()}, {arch} — FEM reference vs real PINN predictions ({ctrl_names}), "
        "live FEniCS, 540°C → 20°C cooldown",
        fontsize=14, fontweight="bold",
    )

    col_titles = ["FEM reference"]
    for ctrl in controllers:
        col_titles += [f"{DISPLAY_NAME[ctrl]}\nprediction", f"{DISPLAY_NAME[ctrl]}\n|error|"]

    for row, t_target in enumerate(SNAPSHOT_TIMES):
        ref_ctrl_idx = idxs[(controllers[0], t_target)]
        ref = d[f"{controllers[0]}_T_ref"][ref_ctrl_idx]  # same FEM field regardless of controller at matching t
        panels = [ref]
        t_labels = []
        for ctrl in controllers:
            i = idxs[(ctrl, t_target)]
            pred = d[f"{ctrl}_T_pred"][i]
            err = np.abs(d[f"{ctrl}_T_ref"][i] - pred)
            panels += [pred, err]
            t_labels.append(f"{DISPLAY_NAME[ctrl]} t={d[f'{ctrl}_t'][i]:.1f}s")

        for col, (field, title) in enumerate(zip(panels, col_titles)):
            ax = axes[row, col]
            if col == 0 or col % 2 == 1:
                sc = draw_field(ax, coords, field, "jet", 20, 540, triang)
                label = "Temperature [°C]"
            else:
                # YlOrRd (pale yellow -> orange -> red), same colormap the
                # thesis's own run_all_domains_compare.py uses for error
                # panels - starts light instead of black, so low-error
                # interior stays legible instead of crushed to near-invisible.
                sc = draw_field(ax, coords, field, "YlOrRd", 0, err_vmax, triang, gamma=0.4)
                label = "|T_ref − T_pred| [°C]"
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
            if row == 0:
                ax.set_title(title, fontsize=11)
            if col == 0:
                ax.set_ylabel(f"t ≈ {t_target:.1f}s\n(" + ", ".join(t_labels) + ")", fontsize=8.5)
            fig.colorbar(sc, ax=ax, pad=0.03, fraction=0.046, label=label if row == 0 else None)

    suffix = "" if arch == "bayesian" else f"_{arch}"
    out_path = figures_dir(geometry) / f"{geometry}_field_comparison{suffix}.png"
    plt.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {out_path}")
    return out_path


def make_trajectory_figure(d: dict, arch: str, geometry: str = "rectangle") -> Path:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.5, 7), sharex=True,
                                    gridspec_kw={"height_ratios": [2.4, 1]}, constrained_layout=True)

    fig.suptitle(f"{geometry.capitalize()}, {arch} — accuracy across the full 540°C → 20°C cooldown",
                 fontsize=13, fontweight="bold")

    ax1.plot(d["algorithm3_t"], d["algorithm3_mae"], "o-", color=COLOR["algorithm3"], label="PINN (threshold)")
    ax1.plot(d["tm_guided_t"], d["tm_guided_mae"], "s--", color=COLOR["tm_guided"], label="PINN+TM")

    for ctrl, va in (("algorithm3", "bottom"), ("tm_guided", "top")):
        t_arr, mae_arr = d[f"{ctrl}_t"], d[f"{ctrl}_mae"]
        offset = 6 if va == "bottom" else -8
        for t, mae in zip(t_arr, mae_arr):
            ax1.annotate(f"{mae:.1f}", (t, mae), textcoords="offset points", xytext=(0, offset),
                         ha="center", fontsize=7, color=COLOR[ctrl])

    ax1.axhline(ACCEPT_THRESH_C, color="black", linestyle=":", linewidth=1.5,
                label=f"safety threshold ({ACCEPT_THRESH_C:.0f}°C)")

    thesis_ref = thesis_reference_mean_mae(arch, geometry)
    if thesis_ref is not None:
        thesis_mae, n_seeds = thesis_ref
        seed_label = f"{n_seeds}-seed mean" if n_seeds > 1 else "single run"
        ax1.axhline(thesis_mae, color="gray", linestyle="-.", linewidth=1.5,
                     label=f"original thesis result (npz FEM h=700, {seed_label}: {thesis_mae:.2f}°C)")

    ax1.set_ylabel("Window MAE [°C]")
    ax1.legend(loc="upper right", fontsize=8.5)
    ax1.grid(alpha=0.3)

    ax2.step(d["algorithm3_t"], d["algorithm3_k"], where="post", color=COLOR["algorithm3"], label="PINN")
    ax2.step(d["tm_guided_t"], d["tm_guided_k"], where="post", color=COLOR["tm_guided"], linestyle="--", label="PINN+TM")
    ax2.set_ylabel("window size k")
    ax2.set_xlabel("time [s]")
    ax2.set_yticks(sorted(set(d["algorithm3_k"].tolist() + d["tm_guided_k"].tolist())))
    ax2.grid(alpha=0.3)
    ax2.legend(loc="upper left", fontsize=9)

    suffix = "" if arch == "bayesian" else f"_{arch}"
    out_path = figures_dir(geometry) / f"{geometry}_mae_trajectory{suffix}.png"
    plt.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {out_path}")
    return out_path


def make_boost_comparison_figure(arch: str, n_windows_shown: int = 3) -> Path | None:
    """Redesign of the old rectangle_loss_curves.png (user rejected the
    single-run version as "not what I wanted", see memory - three
    alternatives were proposed, user picked this one): overlay the
    ORIGINAL 800-epoch/window run (field_snapshots_{arch}_baseline800.npz,
    regenerated on demand from the exact pre-fix config, boost_epochs=0)
    against the FIXED 6400-epoch/window-1-3 run (field_snapshots_{arch}.npz,
    the one already used everywhere else) for the algorithm3 controller -
    this is the same controller both files share, and window 1-3's k
    trajectory is simplest to read (k stays at 1 while MAE is UNSAFE, no
    controller-specific branching yet).

    Only meaningful for nsga2/nsga3 - bayesian's official npz was never
    boosted (it recovers within a couple of windows on its own, see
    memory), so there is nothing to compare it against; returns None and
    skips silently when the baseline file is absent (arch == "bayesian",
    or the baseline sweep hasn't been (re-)run for this arch).
    """
    suffix = "" if arch == "bayesian" else f"_{arch}"
    baseline_path = RESULTS_DIR / f"field_snapshots{suffix}_baseline800.npz"
    if not baseline_path.exists():
        print(f"[skip] no {baseline_path.name} - boost comparison figure needs it (see docstring)")
        return None

    fixed = load(arch)
    baseline = {k: v for k, v in np.load(baseline_path).items()}

    ctrl = "algorithm3"
    fig, axes = plt.subplots(1, n_windows_shown, figsize=(5.2 * n_windows_shown, 4.3),
                              sharey=True, constrained_layout=True)
    fig.suptitle(
        f"Rectangle, {arch} — cold-start freeze: original (800 epochs/window) vs "
        "fixed (6400 epochs, windows 1-3), FEM end-supervision loss",
        fontsize=12.5, fontweight="bold",
    )

    for w in range(n_windows_shown):
        ax = axes[w] if n_windows_shown > 1 else axes
        for run, style, color, label in (
            (baseline, "--", "tab:orange", "original (800 ep)"),
            (fixed, "-", "tab:blue", "fixed (6400 ep)"),
        ):
            loss_end_row = run[f"{ctrl}_loss_end"][w]
            real_len = int(np.sum(~np.isnan(loss_end_row)))
            mae_w = float(run[f"{ctrl}_mae"][w])
            safe = "SAFE" if mae_w <= ACCEPT_THRESH_C else "UNSAFE"
            ax.plot(np.arange(real_len), loss_end_row[:real_len], style, color=color,
                     linewidth=1.3, label=f"{label} — window MAE={mae_w:.1f}°C ({safe})")
        ax.set_yscale("log")
        ax.set_xlim(0, 6400)
        ax.set_title(f"window {w + 1}", fontsize=11)
        ax.set_xlabel("epoch within window")
        ax.grid(alpha=0.25)
        ax.legend(loc="upper right", fontsize=7.5)
    (axes[0] if n_windows_shown > 1 else axes).set_ylabel("FEM end-supervision loss (log scale)")

    out_path = FIGURES_DIR / f"rectangle_boost_comparison{suffix}.png"
    plt.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {out_path}")
    return out_path


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry", default="rectangle", choices=["rectangle", "circle", "lshape"])
    parser.add_argument("--arch", default="bayesian", choices=["bayesian", "nsga2", "nsga3"])
    args = parser.parse_args()

    d = load(args.arch, args.geometry)
    make_field_figure(d, args.arch, args.geometry)
    make_trajectory_figure(d, args.arch, args.geometry)
    if args.geometry == "rectangle":
        make_boost_comparison_figure(args.arch)


if __name__ == "__main__":
    main()
