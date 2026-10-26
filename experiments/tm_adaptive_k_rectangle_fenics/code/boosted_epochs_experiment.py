"""
experiments/tm_adaptive_k_rectangle_fenics/boosted_epochs_experiment.py
=====================================================================
Tests a hypothesis raised while investigating why NSGA-II/NSGA-III are
more fragile than Bayesian on Rectangle: window 1 (t=0->1.5s, the
steepest part of the 540C->20C cooldown) suffers an IDENTICAL "frozen at
IC" collapse for Bayesian AND NSGA-II (grad_mean=pde_residual_mean=0.0
exactly, MAE=8.95C to the last digit, in both raw_runs/*_k1_*.json and
this experiment's live-FEniCS capture) - a consequence of
ThermalPINN.forward's theta_next = clamp(theta_ic + tau*delta, 0, 1): at
window 1, theta_ic=1.0 (T=540C, the max), so any non-negative delta gets
clamped and its gradient zeroed, regardless of architecture. NSGA-III
escapes the freeze but converges to something even worse (MAE=13.8C).

The actual architecture-dependent behaviour is RECOVERY SPEED from that
shared bad start: Bayesian (5x151, ReLU, 92.7k params) recovers by
window 2 (MAE 4.2C); NSGA-II (3x153, tanh, 48.0k params) takes until
window ~6-7; NSGA-III (3x75, tanh, 11.9k params) is worst of all. This
looks like smaller/shallower capacity needing more optimizer steps to
climb out of the same hole, not a controller (Algorithm3/TM) problem -
the controller cannot fix how fast the underlying PINN converges within
a window.

This script tests the fix: give ONLY the first `--boost-windows` windows
a bigger epoch budget (`--boost-epochs`, default 800*4=3200) instead of
the usual 800, for nsga2/nsga3 (and bayesian, for a clean control group),
and check whether that closes the early-window MAE gap. Deliberately
simplified vs field_snapshots.py: no field/loss-history capture (those
require every window to share n_epochs for clean array stacking, which
boosting breaks) - only per-window t/mae/k/n_epochs_used, which is all
that is needed to test this hypothesis.

Output: results/boosted_epochs_{arch}.npz
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_controllers import (
    ACCEPT_THRESH_C, DT_FEM, K_MAX_, K_MIN, T_TOTAL, TRAIN_KWARGS,
    THRESH_DOWN, THRESH_UP, fit_tm_on_all_data, tm_predict_row,
)
from feature_logging_run import compute_window_diagnostics, phase_of, theta_from_domain
from live_fem_reference import LiveFEMReference

from thermal_pinn.network.pinn import make_pinn
from thermal_pinn.training.trainer import K_THERM, evaluate_window, train_window

DIM = 2
MODEL_SEED = 42
RESOLUTION = 30
N_EVAL = 500  # lighter: this experiment only needs mae_C, not dense fields
RESULTS_DIR = Path(__file__).resolve().parent.parent / "npz"


def run(*, controller: str, arch: str, device, boost_epochs: int, boost_windows: int,
        tm_model=None, tm_encoder=None):
    domain = LiveFEMReference(resolution=RESOLUTION)
    torch.manual_seed(MODEL_SEED)
    model = make_pinn(dim=DIM, arch=arch, device=device)

    L_char = float(np.sqrt(domain.Lx * domain.Ly))
    Bi = domain.h * L_char / K_THERM

    k = K_MIN
    t_now = 0.0
    window_idx = 0
    t_list, mae_list, k_list, epochs_used_list = [], [], [], []
    t0_total = time.time()

    print(f"\n=== {controller} arch={arch} (boost_epochs={boost_epochs} "
          f"for first {boost_windows} windows) ===", flush=True)
    while t_now < T_TOTAL - 1e-6:
        dt_window = k * DT_FEM
        t_end = min(t_now + dt_window, T_TOTAL)
        actual_k = round((t_end - t_now) / DT_FEM)
        window_idx += 1
        t_start = t_now

        window_kwargs = dict(TRAIN_KWARGS)
        if window_idx <= boost_windows:
            window_kwargs["n_epochs"] = boost_epochs

        def theta_ic_fn(coords_np, _t=t_start):
            return theta_from_domain(domain, coords_np, _t)

        def theta_end_fn(coords_np, _t=t_end):
            return theta_from_domain(domain, coords_np, _t)

        train_info = train_window(
            model=model, domain=domain, t_start=t_start, t_end=t_end,
            theta_ic_fn=theta_ic_fn, theta_end_fn=theta_end_fn,
            device=device, rng_seed=window_idx, **window_kwargs,
        )
        eval_info = evaluate_window(
            model=model, domain=domain, t_start=t_start, t_end=t_end,
            theta_ic_fn=theta_ic_fn, n_eval=N_EVAL, device=device,
        )
        diag = compute_window_diagnostics(model, domain, t_start, t_end, theta_ic_fn, N_EVAL, device)

        mae = float(eval_info["mae_C"])
        t_list.append(t_end)
        mae_list.append(mae)
        k_list.append(actual_k)
        epochs_used_list.append(window_kwargs["n_epochs"])

        Fo = domain.alpha * (t_end - t_start) / (L_char ** 2)
        true_label = "SAFE" if mae <= ACCEPT_THRESH_C else "UNSAFE"
        final_loss = {
            "loss_pde": float(train_info["loss_pde_history"][-1]),
            "loss_bc": float(train_info["loss_bc_history"][-1]),
            "loss_end": float(train_info["loss_end_history"][-1]),
        }
        row = {"arch": arch, "k": actual_k, "phase": phase_of(t_start),
               "Fo": float(Fo), "Bi": float(Bi), **final_loss, **diag}

        prev_k = actual_k
        if controller == "algorithm3":
            if mae < THRESH_UP and prev_k < K_MAX_:
                next_k = prev_k + 1
            elif mae > THRESH_DOWN and prev_k > K_MIN:
                next_k = prev_k - 1
            else:
                next_k = prev_k
        else:
            tm_pred = tm_predict_row(tm_model, tm_encoder, row)
            next_k = max(K_MIN, prev_k - 1) if tm_pred == "UNSAFE" else min(K_MAX_, prev_k + 1)

        print(f"  [{window_idx:>2}] t={t_end:.1f}s  k={actual_k}  "
              f"n_epochs={window_kwargs['n_epochs']}  MAE={mae:.2f}C  true={true_label}", flush=True)
        k = next_k
        t_now = t_end

    print(f"  done in {time.time() - t0_total:.0f}s, {window_idx} windows", flush=True)
    return {
        "t": np.array(t_list), "mae": np.array(mae_list), "k": np.array(k_list),
        "epochs_used": np.array(epochs_used_list),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch", default="nsga2", choices=["bayesian", "nsga2", "nsga3"])
    parser.add_argument("--boost-epochs", type=int, default=3200)
    parser.add_argument("--boost-windows", type=int, default=2)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    tm_model, tm_encoder = fit_tm_on_all_data(
        bits_per_feature=8, clauses=60, T=10, s=3.0, epochs=50,
    )

    alg3 = run(controller="algorithm3", arch=args.arch, device=device,
               boost_epochs=args.boost_epochs, boost_windows=args.boost_windows)
    tm = run(controller="tm_guided", arch=args.arch, device=device,
              boost_epochs=args.boost_epochs, boost_windows=args.boost_windows,
              tm_model=tm_model, tm_encoder=tm_encoder)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"boosted_epochs_{args.arch}.npz"
    np.savez(
        out_path,
        boost_epochs=np.array(args.boost_epochs), boost_windows=np.array(args.boost_windows),
        algorithm3_t=alg3["t"], algorithm3_mae=alg3["mae"], algorithm3_k=alg3["k"],
        algorithm3_epochs_used=alg3["epochs_used"],
        tm_guided_t=tm["t"], tm_guided_mae=tm["mae"], tm_guided_k=tm["k"],
        tm_guided_epochs_used=tm["epochs_used"],
    )
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
