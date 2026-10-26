"""
thermal_pinn/training/train_pinn_only.py
=========================================
PINN-only training: FEM verisi sadece t=0 başlangıç koşulu ve değerlendirme için.
Her pencere IC'si bir önceki PINN tahmininden interpolasyon ile elde edilir.
End-supervision kapalı — model saf fizik kısıtlamalarıyla öğrenir.

Karşılaştırma:
    FEM-anchored (fem_hT)  : her pencere başında FEM IC kullanır
    PINN-only              : sadece t=0 IC FEM'den, geri kalanı PINN zinciri

Kullanım:
    python -m thermal_pinn.training.train_pinn_only --domain rectangle --arch bayesian --cuda
    python -m thermal_pinn.training.train_pinn_only --all --dim 2 --cuda
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT.parent))

from thermal_pinn.physics.fem_reference import make_reference_domain
from thermal_pinn.physics.domains_2d import DOMAINS_2D
from thermal_pinn.network.pinn import make_pinn, ARCH_CONFIGS
from thermal_pinn.runtime_paths import CHECKPOINT_DIR
from thermal_pinn.training.trainer import train_window, evaluate_window

T_TOTAL  = 30.0
DT_FEM   = 1.5
T_WATER  = 20.0
DELTA_T  = 520.0
N_GRID   = 3000   # interpolation grid density per window

TRAIN_KWARGS = {
    "n_domain":  1500,
    "n_bc":      300,
    "n_epochs":  800,
    "lr":        1e-3,
    "lr_min":    1e-5,
    "lbfgs_iters": 50,
    "use_end_supervision": False,   # PINN-only: no FEM ground truth at window end
}


class _PinnICInterpolator:
    """
    Wrap a set of (x, y, theta) scatter points as a callable IC function.
    theta_ic_fn(coords_np) → theta array.
    """
    def __init__(self, xy: np.ndarray, theta: np.ndarray):
        self._lin  = LinearNDInterpolator(xy, theta)
        self._near = NearestNDInterpolator(xy, theta)

    def __call__(self, coords_np: np.ndarray) -> np.ndarray:
        xy = coords_np[:, :2]
        T  = self._lin(xy)
        nan_mask = np.isnan(T)
        if nan_mask.any():
            T[nan_mask] = self._near(xy[nan_mask])
        return T.astype(np.float32)


def _eval_pinn_on_grid(
    model: torch.nn.Module,
    domain,
    ic_fn,
    rng: np.random.Generator,
    n: int = N_GRID,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Evaluate model at tau=1 on a random interior grid.
    Returns (xy_phys, theta_pred) for building the next window's IC interpolator.
    """
    from thermal_pinn.training.trainer import _normalise_coords
    dev = next(model.parameters()).device

    xi, yi = domain.sample_interior(n, rng=rng)
    coords_np   = np.stack([xi, yi], axis=1).astype(np.float32)
    coords_norm = _normalise_coords(coords_np, domain)
    theta_ic    = ic_fn(coords_np).reshape(-1, 1)

    coords_t   = torch.tensor(coords_norm).to(dev)
    tau_one    = torch.ones(len(coords_np), 1, device=dev)
    theta_ic_t = torch.tensor(theta_ic).to(dev)

    model.eval()
    with torch.no_grad():
        theta_pred = model(coords_t, tau_one, theta_ic_t).cpu().numpy().flatten()

    return coords_np, theta_pred


def run_pinn_only(
    domain_name: str,
    arch: str,
    dim: int,
    device: torch.device,
    k: int = 1,
    tag: str = "",
    verbose: bool = True,
) -> dict:
    """
    Full 30-second simulation — PINN-only mode, k=fixed window width.
    IC at each window = previous window's PINN output (interpolated).
    No end supervision; FEM data used only for evaluation.
    """
    if dim != 2:
        raise NotImplementedError("PINN-only currently 2D only.")

    domain = make_reference_domain(domain_name, dim=2)
    model  = make_pinn(dim=2, arch=arch, device=device)

    dt_window = k * DT_FEM
    anchors   = np.arange(0.0, T_TOTAL - dt_window / 2, dt_window)
    rng       = np.random.default_rng(42)

    window_results = []
    t0_total = time.time()

    # Uniform IC at t=0: T=540°C → θ=1.0 everywhere
    current_ic_fn = lambda coords_np: np.ones(len(coords_np), dtype=np.float32)

    if verbose:
        print(f"\n{'='*60}")
        print(f"  PINN-ONLY  domain={domain_name}  arch={arch}  k={k}  dim={dim}D")
        print(f"  No end-supervision — chained PINN IC")
        print(f"{'='*60}", flush=True)

    for i, t_start in enumerate(anchors):
        t_end = min(t_start + dt_window, T_TOTAL)

        if verbose:
            print(f"  [{i+1}/{len(anchors)}] Window [{t_start:.1f}→{t_end:.1f}s]  k={k}",
                  flush=True)

        ic_fn_capture = current_ic_fn  # closure capture

        def theta_ic_fn(coords_np, _ic=ic_fn_capture):
            return _ic(coords_np)

        train_info = train_window(
            model=model, domain=domain,
            t_start=t_start, t_end=t_end,
            theta_ic_fn=theta_ic_fn,
            theta_end_fn=None,
            device=device,
            rng_seed=i,
            **TRAIN_KWARGS,
        )

        # Evaluate vs FEM reference
        eval_info = evaluate_window(
            model=model, domain=domain,
            t_start=t_start, t_end=t_end,
            theta_ic_fn=theta_ic_fn,
            device=device,
        )

        if verbose:
            print(f"      MAE={eval_info['mae_C']:.2f}°C  "
                  f"L2={eval_info['l2_rel']:.4f}  "
                  f"({train_info['runtime_s']:.0f}s)", flush=True)

        window_results.append({
            "window":   i + 1,
            "t_start":  float(t_start),
            "t_end":    float(t_end),
            "k_used":   k,
            "mae_C":    eval_info["mae_C"],
            "l2_rel":   eval_info["l2_rel"],
            "runtime_s": train_info["runtime_s"],
        })

        # Build PINN IC interpolator for next window
        grid_coords, theta_grid = _eval_pinn_on_grid(
            model, domain, theta_ic_fn, rng, n=N_GRID
        )
        current_ic_fn = _PinnICInterpolator(grid_coords[:, :2], theta_grid)

    mean_mae = float(np.mean([w["mae_C"] for w in window_results]))
    total_t  = time.time() - t0_total

    if verbose:
        print(f"\n  RESULT  mean MAE={mean_mae:.2f}°C  "
              f"windows={len(window_results)}  total={total_t:.0f}s", flush=True)

    # Save
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    tag_part = f"_{tag.strip('_')}" if tag else ""
    stem = f"{domain_name}_{arch}_pinn_only{tag_part}_k{k}_dim{dim}"

    ckpt_path = CHECKPOINT_DIR / f"{stem}.pt"
    torch.save({
        "model_state": model.state_dict(),
        "arch":  arch, "dim": dim, "domain": domain_name,
        "k": k, "mean_mae": mean_mae, "windows": window_results,
    }, ckpt_path)

    result = {
        "domain":     domain_name,
        "arch":       arch,
        "strategy":   "pinn_only_chained",
        "reference_used_each_window": False,
        "reference_used_for_final_evaluation": True,
        "k":          k,
        "dim":        dim,
        "mean_mae":   mean_mae,
        "n_windows":  len(window_results),
        "windows":    window_results,
        "total_s":    total_t,
        "checkpoint": str(ckpt_path),
    }
    metrics_path = CHECKPOINT_DIR / f"{stem}_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(result, f, indent=2)

    if verbose:
        print(f"  → Saved: {ckpt_path.name}", flush=True)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="PINN-only training — no FEM anchoring per window."
    )
    parser.add_argument("--domain", default="rectangle",
                        choices=list(DOMAINS_2D))
    parser.add_argument("--arch", default="bayesian", choices=list(ARCH_CONFIGS))
    parser.add_argument("--k",    type=int, default=1,
                        help="Window width in FEM steps (default: 1)")
    parser.add_argument("--dim",  type=int, default=2, choices=[2])
    parser.add_argument("--all",  action="store_true",
                        help="Run for all 2D domains")
    parser.add_argument("--tag",  default="fem_hT",
                        help="Output tag (default: fem_hT for consistency)")
    parser.add_argument("--cuda", action="store_true")
    args = parser.parse_args()

    device = torch.device("cuda" if args.cuda and torch.cuda.is_available() else "cpu")
    print(f"Device: {device}", flush=True)

    if args.all:
        for domain_name in ("rectangle", "circle", "lshape"):
            run_pinn_only(domain_name, args.arch, args.dim, device,
                          k=args.k, tag=args.tag)
    else:
        run_pinn_only(args.domain, args.arch, args.dim, device,
                      k=args.k, tag=args.tag)


if __name__ == "__main__":
    main()
