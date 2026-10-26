"""
experiments/tm_adaptive_k_rectangle/feature_logging_run.py
============================================================
Re-runs the existing FIXED-k sweep (thermal_pinn/training/train_all.py,
function run_one) for the Rectangle domain, one architecture at a time,
and additionally logs, at the end of every window, the extra physics-based
features the TM controller will need:

    pde_residual_mean / pde_residual_max   (|dtheta/dtau - alpha_eff*laplacian|)
    grad_mean / grad_max                   (||d theta / d x_norm||)
    delta_T_C                              (mean |T_pred - T_ic| over the window)
    Fo, Bi                                 (dimensionless numbers, Section 2.1.3)
    phase                                  (early/mid/late, t<10s / 10-20s / >=20s)
    label                                  (SAFE if mae_C <= ACCEPT_THRESH_C else UNSAFE)

Why the fixed-k sweep instead of the adaptive trajectory
----------------------------------------------------------
A single adaptive-k run only ever visits ONE k per window, so it tells us
almost nothing about whether the *other* k values would have been safe at
that same point in time (and, for Rectangle, the SAFE/UNSAFE label turns out
to be almost always SAFE along that one trajectory - see
thermal_pinn_adaptive_k_warmstart memory). The existing fixed-k sweep
checkpoints (checkpoints/rectangle_<arch>_k{1..5}_dim2_v2_metrics.json)
already show, for every window position, whether EVERY k in {1..5} keeps
the MAE under the engineering acceptance threshold - this is exactly the
"known fixed-k optimum of each architecture" the thesis's own Future Work
section (conclusion.tex) says a deployment-ready controller should be
calibrated against. This script reproduces that fixed-k sweep (same loop
as train_all.py's run_one - model NOT reset between windows within one k,
rng_seed = i, same train_kwargs) and layers the extra diagnostics on top,
so the TM sees, for every (k, window) combination, both the outcome
(mae_C / SAFE-UNSAFE) and the FEM-free signals available before that
window was trained.

This script only *imports* from the existing thermal_pinn package - it
does not modify any existing file.

Usage
-----
    # Smoke test (fast, tiny settings):
    python -m thermal_pinn.experiments.tm_adaptive_k_rectangle.feature_logging_run \\
        --arch bayesian --k-values 1 2 --n-epochs 2 --lbfgs-iters 1 \\
        --n-eval 16 --max-windows 2 --device cpu

    # Real run - bayesian only, all 5 fixed k values, Rectangle, GPU:
    python -m thermal_pinn.experiments.tm_adaptive_k_rectangle.feature_logging_run \\
        --arch bayesian --k-values 1 2 3 4 5 --cuda
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

from thermal_pinn.network.pinn import ARCH_CONFIGS, make_pinn
from thermal_pinn.physics.fem_reference import make_reference_domain
from thermal_pinn.training.trainer import (
    K_THERM,
    evaluate_window,
    train_window,
    _normalise_coords,
)

DOMAIN_NAME = "rectangle"
DIM = 2
T_TOTAL = 30.0
DT_FEM = 1.5
T_WATER = 20.0
DELTA_T = 520.0

TRAIN_KWARGS = {
    "n_domain": 1500,
    "n_bc": 300,
    "n_epochs": 800,
    "lr": 1e-3,
    "lr_min": 1e-5,
    "lbfgs_iters": 50,
    "use_end_supervision": True,
}

# Engineering acceptance threshold for the 2D canonical domains (Rectangle /
# Circle / L-shape), taken from reports/thesis_uia/chapters/results_2d.tex
# table legend: "within 10 C".
ACCEPT_THRESH_C = 10.0

EARLY_UNTIL = 10.0
MID_UNTIL = 20.0

OUT_DIR = Path(__file__).resolve().parent / "raw_runs"


def theta_from_domain(domain, coords_np: np.ndarray, t: float) -> np.ndarray:
    T_vals = domain.T(coords_np[:, 0], coords_np[:, 1], t)
    T_vals = np.where(np.isfinite(T_vals), T_vals, T_WATER)
    return ((T_vals - T_WATER) / DELTA_T).astype(np.float32)


def compute_window_diagnostics(
    model, domain, t_start: float, t_end: float, theta_ic_fn, n_eval: int, device: torch.device
) -> dict:
    """PDE residual + spatial-gradient diagnostics at tau=1 (window end).

    Reuses the exact same eval points as evaluate_window (rng seed 42), and
    the exact same residual formula as trainer._pde_residual, but returns
    per-point mean/max instead of a single reduced MSE, and does not use
    torch.no_grad() (autograd is needed for the residual/gradient).
    """
    rng = np.random.default_rng(42)
    xi, yi = domain.sample_interior(n_eval, rng=rng)
    coords_np = np.stack([xi, yi], axis=1)

    coords_norm = _normalise_coords(coords_np, domain)
    theta_ic_np = theta_ic_fn(coords_np).reshape(-1, 1).astype(np.float32)

    coords_t = torch.tensor(coords_norm, dtype=torch.float32, device=device).requires_grad_(True)
    tau_t = torch.ones(n_eval, 1, device=device).requires_grad_(True)
    theta_ic_t = torch.tensor(theta_ic_np, dtype=torch.float32, device=device)

    model.eval()
    theta = model(coords_t, tau_t, theta_ic_t)

    dtheta_dtau = torch.autograd.grad(
        theta, tau_t, grad_outputs=torch.ones_like(theta),
        create_graph=True, retain_graph=True,
    )[0]

    grads = torch.autograd.grad(
        theta, coords_t, grad_outputs=torch.ones_like(theta),
        create_graph=True, retain_graph=True,
    )[0]

    laplacian = torch.zeros_like(theta)
    for i in range(coords_t.shape[1]):
        d2 = torch.autograd.grad(
            grads[:, i:i + 1], coords_t, grad_outputs=torch.ones_like(grads[:, i:i + 1]),
            retain_graph=True,
        )[0][:, i:i + 1]
        laplacian = laplacian + d2

    alpha = getattr(domain, "alpha", 6.25e-5)
    dt_window = t_end - t_start
    alpha_eff = alpha * dt_window
    residual = (dtheta_dtau - alpha_eff * laplacian).detach().abs().cpu().numpy().flatten()
    grad_norm = grads.detach().norm(dim=1).cpu().numpy()

    T_pred = T_WATER + DELTA_T * theta.detach().cpu().numpy().flatten()
    T_ic = T_WATER + DELTA_T * theta_ic_np.flatten()
    delta_T_C = float(np.mean(np.abs(T_pred - T_ic)))

    return {
        "pde_residual_mean": float(residual.mean()),
        "pde_residual_max": float(residual.max()),
        "grad_mean": float(grad_norm.mean()),
        "grad_max": float(grad_norm.max()),
        "delta_T_C": delta_T_C,
    }


def phase_of(t_start: float) -> str:
    if t_start < EARLY_UNTIL:
        return "early"
    if t_start < MID_UNTIL:
        return "mid"
    return "late"


def run_fixed_k(arch: str, k: int, device: torch.device, train_kwargs: dict,
                 n_eval: int, max_windows: int | None, seed_base: int, verbose: bool) -> dict:
    """Fixed-k sweep for one (arch, k), mirroring train_all.py's run_one()
    exactly (same model reused across windows, same rng_seed=seed_base+i),
    plus the extra window-end diagnostics."""
    domain = make_reference_domain(DOMAIN_NAME, dim=DIM)
    model = make_pinn(dim=DIM, arch=arch, device=device)

    Lx, Ly = domain.Lx, domain.Ly
    L_char = float(np.sqrt(Lx * Ly))
    h = getattr(domain, "h", 700.0)
    alpha = getattr(domain, "alpha", 6.25e-5)
    Bi = h * L_char / K_THERM

    dt_window = k * DT_FEM
    anchors = np.arange(0.0, T_TOTAL - dt_window / 2, dt_window)
    if max_windows is not None:
        anchors = anchors[:max_windows]

    window_results = []
    t0_total = time.time()

    if verbose:
        print(f"[{arch} k={k}] {len(anchors)} windows", flush=True)

    for i, t_start in enumerate(anchors):
        t_end = min(t_start + dt_window, T_TOTAL)

        def theta_ic_fn(coords_np, _t=t_start):
            return theta_from_domain(domain, coords_np, _t)

        def theta_end_fn(coords_np, _t=t_end):
            return theta_from_domain(domain, coords_np, _t)

        train_info = train_window(
            model=model, domain=domain, t_start=t_start, t_end=t_end,
            theta_ic_fn=theta_ic_fn, theta_end_fn=theta_end_fn,
            device=device, rng_seed=seed_base + i, **train_kwargs,
        )
        eval_info = evaluate_window(
            model=model, domain=domain, t_start=t_start, t_end=t_end,
            theta_ic_fn=theta_ic_fn, n_eval=n_eval, device=device,
        )
        diag = compute_window_diagnostics(
            model, domain, t_start, t_end, theta_ic_fn, n_eval, device,
        )

        mae = float(eval_info["mae_C"])
        l2 = float(eval_info["l2_rel"])
        Fo = alpha * (t_end - t_start) / (L_char ** 2)
        label = "SAFE" if mae <= ACCEPT_THRESH_C else "UNSAFE"

        final_loss = {
            "loss_pde": float(train_info["loss_pde_history"][-1]),
            "loss_bc": float(train_info["loss_bc_history"][-1]),
            "loss_ic": float(train_info["loss_ic_history"][-1]),
            "loss_end": float(train_info["loss_end_history"][-1]),
        }

        if verbose:
            print(
                f"  [{i + 1:>2}/{len(anchors)}] [{t_start:.1f}->{t_end:.1f}s] k={k}  "
                f"MAE={mae:.2f}C  L2={l2:.4f}  "
                f"loss(pde={final_loss['loss_pde']:.2e} bc={final_loss['loss_bc']:.2e} "
                f"ic={final_loss['loss_ic']:.2e} end={final_loss['loss_end']:.2e})  "
                f"res_mean={diag['pde_residual_mean']:.2e}  grad_mean={diag['grad_mean']:.2e}  "
                f"label={label}  ({train_info['runtime_s']:.0f}s)", flush=True,
            )

        window_results.append({
            "window": i + 1,
            "t_start": float(t_start),
            "t_end": float(t_end),
            "k": k,
            "mae_C": mae,
            "l2_rel": l2,
            "runtime_s": float(train_info["runtime_s"]),
            "phase": phase_of(t_start),
            "Fo": float(Fo),
            "Bi": float(Bi),
            "label": label,
            **final_loss,
            **diag,
        })

    mean_mae = float(np.mean([w["mae_C"] for w in window_results])) if window_results else float("nan")

    return {
        "domain": DOMAIN_NAME,
        "arch": arch,
        "dim": DIM,
        "k": k,
        "mode": "fixed_k_sweep",
        "accept_thresh_C": ACCEPT_THRESH_C,
        "mean_mae": mean_mae,
        "n_windows": len(window_results),
        "total_s": time.time() - t0_total,
        "train_kwargs": train_kwargs,
        "windows": window_results,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Rectangle fixed-k sweep feature-logging re-run.")
    p.add_argument("--arch", default="bayesian", choices=list(ARCH_CONFIGS))
    p.add_argument("--k-values", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    p.add_argument("--n-epochs", type=int, default=None)
    p.add_argument("--lbfgs-iters", type=int, default=None)
    p.add_argument("--n-eval", type=int, default=500)
    p.add_argument("--max-windows", type=int, default=None)
    p.add_argument("--seed-base", type=int, default=0)
    p.add_argument("--cuda", action="store_true")
    p.add_argument("--device", default=None)
    p.add_argument("--quiet", action="store_true")
    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.device is not None:
        device = torch.device(args.device)
    elif args.cuda:
        device = torch.device("cuda")
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    train_kwargs = dict(TRAIN_KWARGS)
    if args.n_epochs is not None:
        train_kwargs["n_epochs"] = args.n_epochs
    if args.lbfgs_iters is not None:
        train_kwargs["lbfgs_iters"] = args.lbfgs_iters

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Device: {device}", flush=True)

    for k in args.k_values:
        result = run_fixed_k(
            args.arch, k, device, train_kwargs, args.n_eval, args.max_windows,
            args.seed_base, verbose=not args.quiet,
        )
        out_path = OUT_DIR / f"rectangle_{args.arch}_k{k}_dim2_features.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(
            f"[{args.arch} k={k}] mean_mae={result['mean_mae']:.2f}C  "
            f"n_windows={result['n_windows']}  -> {out_path.name}", flush=True,
        )


if __name__ == "__main__":
    main()
