"""
experiments/tm_adaptive_k_rectangle_fenics/feature_logging_run.py
=====================================================================
Same fixed-k sweep + feature-logging design as
experiments/tm_adaptive_k_rectangle/feature_logging_run.py, but using the
REAL, live FEniCS solver (LiveFEMReference) instead of the pre-computed
fem_hT_rectangle.npz interpolation. Everything else - train_window,
evaluate_window, make_pinn, the residual/gradient diagnostics, the window
loop structure (model NOT reset between windows within one k, matching
train_all.py's run_one) - is identical, so the two experiments are directly
comparable except for the FEM reference itself.

Usage
-----
    # Smoke test:
    python -m thermal_pinn.experiments.tm_adaptive_k_rectangle_fenics.code.feature_logging_run \\
        --k-values 1 2 --n-epochs 5 --lbfgs-iters 2 --n-eval 16 --max-windows 2 \\
        --resolution 15 --device cpu

    # Real run - bayesian, Rectangle, all 5 fixed k values, live FEniCS FEM:
    python -m thermal_pinn.experiments.tm_adaptive_k_rectangle_fenics.code.feature_logging_run \\
        --k-values 1 2 3 4 5 --cuda
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

from thermal_pinn.network.pinn import ARCH_CONFIGS, make_pinn
from thermal_pinn.training.trainer import K_THERM, evaluate_window, train_window, _normalise_coords
from thermal_pinn.experiments.tm_adaptive_k_rectangle_fenics.code.live_fem_reference import LiveFEMReference
from thermal_pinn.experiments.tm_adaptive_k_rectangle_fenics.code.hybrid_controller import retry_until_safe

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

ACCEPT_THRESH_C = 10.0  # results_2d.tex legend: "within 10 C"
EARLY_UNTIL = 10.0
MID_UNTIL = 20.0

OUT_DIR = Path(__file__).resolve().parent.parent / "raw_runs"


def theta_from_domain(domain, coords_np: np.ndarray, t: float) -> np.ndarray:
    T_vals = domain.T(coords_np[:, 0], coords_np[:, 1], t)
    T_vals = np.where(np.isfinite(T_vals), T_vals, T_WATER)
    return ((T_vals - T_WATER) / DELTA_T).astype(np.float32)


def compute_window_diagnostics(model, domain, t_start, t_end, theta_ic_fn, n_eval, device) -> dict:
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
        theta, tau_t, grad_outputs=torch.ones_like(theta), create_graph=True, retain_graph=True,
    )[0]
    grads = torch.autograd.grad(
        theta, coords_t, grad_outputs=torch.ones_like(theta), create_graph=True, retain_graph=True,
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
                 n_eval: int, max_windows, resolution: int, seed_base: int,
                 model_seed: int, verbose: bool, tm_boosted: bool = False,
                 geometry: str = "rectangle") -> dict:
    """tm_boosted: if True, wrap each window's training in
    hybrid_controller.retry_until_safe() - keep training IN PLACE in
    RETRY_INCREMENT-epoch slices, re-evaluating each time, until the
    window is SAFE (mae_C <= ACCEPT_THRESH_C) or the 6400-epoch ceiling
    is hit. Produces a clean, always-SAFE-where-possible reference sweep
    per k, instead of the plain single-pass 800-epoch sweep this
    function normally does - see the user's "Fikir 2" request in
    tm_adaptive_k_rectangle_experiment.md memory: a TM-boosted per-k
    reference table to feed recommend_k.py better numbers than the raw,
    uncorrected sweep."""
    domain = LiveFEMReference(geometry=geometry, resolution=resolution)
    # Fix the model's weight initialisation so every k in the sweep starts
    # from the IDENTICAL initial network - isolates the effect of k itself
    # instead of confounding it with random-init variance (this is what
    # caused the window-1 dying-ReLU collapse seen at k=3/k=4 previously,
    # since make_pinn's Linear layers were drawing from the unseeded
    # global torch RNG on every call).
    torch.manual_seed(model_seed)
    model = make_pinn(dim=DIM, arch=arch, device=device)

    L_char = float(np.sqrt(domain.Lx * domain.Ly))
    Bi = domain.h * L_char / K_THERM

    dt_window = k * DT_FEM
    anchors = np.arange(0.0, T_TOTAL - dt_window / 2, dt_window)
    if max_windows is not None:
        anchors = anchors[:max_windows]

    window_results = []
    t0_total = time.time()
    if verbose:
        print(f"[{arch} k={k}] {len(anchors)} windows (live FEniCS, resolution={resolution})", flush=True)

    for i, t_start in enumerate(anchors):
        t_end = min(t_start + dt_window, T_TOTAL)

        def theta_ic_fn(coords_np, _t=t_start):
            return theta_from_domain(domain, coords_np, _t)

        def theta_end_fn(coords_np, _t=t_end):
            return theta_from_domain(domain, coords_np, _t)

        retry_count, n_epochs_used = 0, train_kwargs["n_epochs"]
        if tm_boosted:
            attempt = [0]
            cumulative_runtime = [0.0]

            def train_epochs_fn(n_epochs, _i=i, _attempt=attempt, _rt=cumulative_runtime):
                _attempt[0] += 1
                # First attempt uses the SAME seed as the plain (non-boosted)
                # sweep (rng_seed=seed_base+i) so a 0-retry window is
                # seed-identical to the plain sweep - only actual retries
                # get a distinct seed.
                seed = (seed_base + _i) if _attempt[0] == 1 else (seed_base + _i) * 1000 + _attempt[0]
                info = train_window(
                    model=model, domain=domain, t_start=t_start, t_end=t_end,
                    theta_ic_fn=theta_ic_fn, theta_end_fn=theta_end_fn,
                    device=device, rng_seed=seed,
                    **{**train_kwargs, "n_epochs": n_epochs},
                )
                _rt[0] += info["runtime_s"]
                return info

            def eval_fn():
                return evaluate_window(
                    model=model, domain=domain, t_start=t_start, t_end=t_end,
                    theta_ic_fn=theta_ic_fn, n_eval=n_eval, device=device,
                )

            retry_result = retry_until_safe(
                train_epochs_fn=train_epochs_fn, eval_fn=eval_fn,
                base_epochs=train_kwargs["n_epochs"], accept_thresh_C=ACCEPT_THRESH_C,
            )
            train_info, eval_info = retry_result.train_info, retry_result.eval_info
            retry_count, n_epochs_used = retry_result.retry_count, retry_result.total_epochs
            train_info = {**train_info, "runtime_s": cumulative_runtime[0]}
        else:
            train_info = train_window(
                model=model, domain=domain, t_start=t_start, t_end=t_end,
                theta_ic_fn=theta_ic_fn, theta_end_fn=theta_end_fn,
                device=device, rng_seed=seed_base + i, **train_kwargs,
            )
            eval_info = evaluate_window(
                model=model, domain=domain, t_start=t_start, t_end=t_end,
                theta_ic_fn=theta_ic_fn, n_eval=n_eval, device=device,
            )
        diag = compute_window_diagnostics(model, domain, t_start, t_end, theta_ic_fn, n_eval, device)

        mae = float(eval_info["mae_C"])
        l2 = float(eval_info["l2_rel"])
        Fo = domain.alpha * (t_end - t_start) / (L_char ** 2)
        label = "SAFE" if mae <= ACCEPT_THRESH_C else "UNSAFE"

        final_loss = {
            "loss_pde": float(train_info["loss_pde_history"][-1]),
            "loss_bc": float(train_info["loss_bc_history"][-1]),
            "loss_ic": float(train_info["loss_ic_history"][-1]),
            "loss_end": float(train_info["loss_end_history"][-1]),
        }

        retry_note = f"  [retried {retry_count}x -> {n_epochs_used}ep]" if retry_count else ""
        if verbose:
            print(
                f"  [{i + 1:>2}/{len(anchors)}] [{t_start:.1f}->{t_end:.1f}s] k={k}  "
                f"MAE={mae:.2f}C  L2={l2:.4f}{retry_note}  "
                f"loss(pde={final_loss['loss_pde']:.2e} bc={final_loss['loss_bc']:.2e} "
                f"ic={final_loss['loss_ic']:.2e} end={final_loss['loss_end']:.2e})  "
                f"res_mean={diag['pde_residual_mean']:.2e}  grad_mean={diag['grad_mean']:.2e}  "
                f"label={label}  ({train_info['runtime_s']:.0f}s)", flush=True,
            )

        window_results.append({
            "window": i + 1, "t_start": float(t_start), "t_end": float(t_end), "k": k,
            "mae_C": mae, "l2_rel": l2, "runtime_s": float(train_info["runtime_s"]),
            "phase": phase_of(t_start), "Fo": float(Fo), "Bi": float(Bi), "label": label,
            "retry_count": retry_count, "n_epochs_used": int(n_epochs_used),
            **final_loss, **diag,
        })

    mean_mae = float(np.mean([w["mae_C"] for w in window_results])) if window_results else float("nan")
    return {
        "domain": DOMAIN_NAME, "arch": arch, "dim": DIM, "k": k,
        "mode": "fixed_k_sweep_live_fenics", "fem_engine": "FEniCS/dolfin (live)",
        "resolution": resolution, "model_seed": model_seed, "accept_thresh_C": ACCEPT_THRESH_C,
        "mean_mae": mean_mae, "n_windows": len(window_results),
        "total_s": time.time() - t0_total, "train_kwargs": train_kwargs,
        "windows": window_results,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fixed-k sweep, live FEniCS reference.")
    p.add_argument("--geometry", default="rectangle", choices=["rectangle", "circle", "lshape"])
    p.add_argument("--arch", default="bayesian", choices=list(ARCH_CONFIGS))
    p.add_argument("--k-values", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    p.add_argument("--resolution", type=int, default=30, help="mshr mesh resolution")
    p.add_argument("--n-epochs", type=int, default=None)
    p.add_argument("--lbfgs-iters", type=int, default=None)
    p.add_argument("--n-eval", type=int, default=500)
    p.add_argument("--max-windows", type=int, default=None)
    p.add_argument("--seed-base", type=int, default=0)
    p.add_argument("--model-seed", type=int, default=42,
                    help="torch.manual_seed() before building the model - identical across all k values in the sweep")
    p.add_argument("--cuda", action="store_true")
    p.add_argument("--device", default=None)
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--tm-boosted", action="store_true",
                    help="Wrap each window in hybrid_controller.retry_until_safe() - keep "
                         "training in place until SAFE or the 6400-epoch ceiling, instead "
                         "of a single 800-epoch pass. Output filename gets a _tmboosted "
                         "suffix so it doesn't overwrite the plain sweep.")
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

    # rectangle keeps the original flat raw_runs/ layout (backward compat with
    # 2 days of existing rectangle results); circle/lshape get their own
    # raw_runs/{geometry}/ subfolder so nothing gets mixed together (see
    # tm_adaptive_k_rectangle_experiment.md memory: "Ortak kod + geometriye
    # göre ayrı sonuç klasörleri" decision, 2026-09-15).
    out_dir = OUT_DIR / args.geometry
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Device: {device}  geometry: {args.geometry}", flush=True)

    tag = "_tmboosted" if args.tm_boosted else ""
    for k in args.k_values:
        result = run_fixed_k(
            args.arch, k, device, train_kwargs, args.n_eval, args.max_windows,
            args.resolution, args.seed_base, args.model_seed, verbose=not args.quiet,
            tm_boosted=args.tm_boosted, geometry=args.geometry,
        )
        out_path = out_dir / f"{args.geometry}_{args.arch}_k{k}_dim2_live_features{tag}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        n_unsafe = sum(1 for w in result["windows"] if w["label"] == "UNSAFE")
        print(
            f"[{args.arch} k={k}] mean_mae={result['mean_mae']:.2f}C  "
            f"n_windows={result['n_windows']}  n_unsafe={n_unsafe}  -> {out_path.name}", flush=True,
        )


if __name__ == "__main__":
    main()
