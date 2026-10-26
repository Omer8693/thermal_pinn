"""
experiments/tm_adaptive_k_rectangle_fenics/field_snapshots_warmstart_adaptive.py
=====================================================================
Second iteration of the persistent-optimizer experiment
(field_snapshots_warmstart.py): a FIXED continuation_lr=1e-4 eliminated
the window-transition loss "kick" but under-fit windows where k jumped
up a lot (the physically harder window did not get enough optimizer
"search room" within its fixed 800-epoch budget - see
rectangle_warmstart_comparison.png: PINN+TM's MAE got noticeably worse
at t=4.5-9s, right where k grows fastest).

Fix tried here: scale continuation_lr by how much harder the window just
got, instead of using one fixed value for every window:

    ratio = k_current / k_previous
    continuation_lr = clip(BASE_LOW * ratio**2, LR_FLOOR, lr)

- k unchanged or shrinking (ratio <= 1): continuation_lr stays at/below
  BASE_LOW (1e-4) - these windows are the same difficulty or easier than
  the one the model just converged on, so a gentle refine is enough and
  there is no reason to re-kick the weights.
- k growing (ratio > 1): continuation_lr grows quadratically with the
  jump, e.g. a k: 1->2 doubling gives ratio=2 -> continuation_lr=4e-4;
  a big jump can approach the original lr=1e-3 (full reset) again, which
  is exactly the amount of "search room" the original fresh-Adam version
  was implicitly relying on for hard windows.

Output: results/field_snapshots_warmstart_adaptive.npz, same schema as
field_snapshots.npz / field_snapshots_warmstart.npz.
"""

from __future__ import annotations

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
from persistent_trainer import train_window_persistent

from thermal_pinn.network.pinn import make_pinn
from thermal_pinn.training.trainer import K_THERM, evaluate_window

DIM = 2
ARCH = "bayesian"
MODEL_SEED = 42
RESOLUTION = 30
N_EVAL = 2500
RESULTS_DIR = Path(__file__).resolve().parent.parent / "npz"

BASE_LOW = 1e-4
LR_FLOOR = 1e-5


def adaptive_continuation_lr(k_current: int, k_previous: int, lr: float) -> float:
    ratio = k_current / max(k_previous, 1)
    value = BASE_LOW * (ratio ** 2)
    return float(np.clip(value, LR_FLOOR, lr))


def run_with_field_capture(*, controller: str, device, tm_model=None, tm_encoder=None):
    domain = LiveFEMReference(resolution=RESOLUTION)
    torch.manual_seed(MODEL_SEED)
    model = make_pinn(dim=DIM, arch=ARCH, device=device)
    opt_state: dict = {}

    L_char = float(np.sqrt(domain.Lx * domain.Ly))
    Bi = domain.h * L_char / K_THERM

    k = K_MIN
    prev_actual_k = None
    t_now = 0.0
    window_idx = 0
    t_list, mae_list, k_list, runtime_list, clr_list = [], [], [], [], []
    T_ref_list, T_pred_list = [], []
    loss_total_list, loss_pde_list, loss_bc_list, loss_end_list = [], [], [], []
    coords_shared = None
    t0_total = time.time()

    print(f"\n=== {controller} (adaptive persistent-optimizer field capture) ===", flush=True)
    while t_now < T_TOTAL - 1e-6:
        dt_window = k * DT_FEM
        t_end = min(t_now + dt_window, T_TOTAL)
        actual_k = round((t_end - t_now) / DT_FEM)
        window_idx += 1
        t_start = t_now

        base_lr = TRAIN_KWARGS["lr"]
        continuation_lr = (
            base_lr if prev_actual_k is None
            else adaptive_continuation_lr(actual_k, prev_actual_k, base_lr)
        )

        def theta_ic_fn(coords_np, _t=t_start):
            return theta_from_domain(domain, coords_np, _t)

        def theta_end_fn(coords_np, _t=t_end):
            return theta_from_domain(domain, coords_np, _t)

        train_info = train_window_persistent(
            model=model, domain=domain, t_start=t_start, t_end=t_end,
            theta_ic_fn=theta_ic_fn, theta_end_fn=theta_end_fn,
            opt_state=opt_state, continuation_lr=continuation_lr,
            device=device, rng_seed=window_idx, **TRAIN_KWARGS,
        )
        eval_info = evaluate_window(
            model=model, domain=domain, t_start=t_start, t_end=t_end,
            theta_ic_fn=theta_ic_fn, n_eval=N_EVAL, device=device,
        )
        diag = compute_window_diagnostics(model, domain, t_start, t_end, theta_ic_fn, N_EVAL, device)

        mae = float(eval_info["mae_C"])
        if coords_shared is None:
            coords_shared = eval_info["coords"]
        t_list.append(t_end)
        mae_list.append(mae)
        k_list.append(actual_k)
        clr_list.append(continuation_lr)
        runtime_list.append(float(train_info["runtime_s"]))
        T_ref_list.append(eval_info["T_ref"])
        T_pred_list.append(eval_info["T_pred"])
        loss_total_list.append(np.asarray(train_info["loss_history"], dtype=np.float64))
        loss_pde_list.append(np.asarray(train_info["loss_pde_history"], dtype=np.float64))
        loss_bc_list.append(np.asarray(train_info["loss_bc_history"], dtype=np.float64))
        loss_end_list.append(np.asarray(train_info["loss_end_history"], dtype=np.float64))

        Fo = domain.alpha * (t_end - t_start) / (L_char ** 2)
        true_label = "SAFE" if mae <= ACCEPT_THRESH_C else "UNSAFE"
        final_loss = {
            "loss_pde": float(train_info["loss_pde_history"][-1]),
            "loss_bc": float(train_info["loss_bc_history"][-1]),
            "loss_end": float(train_info["loss_end_history"][-1]),
        }
        row = {"arch": ARCH, "k": actual_k, "phase": phase_of(t_start),
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

        print(f"  [{window_idx:>2}] t={t_end:.1f}s  k={actual_k}  MAE={mae:.2f}C  "
              f"true={true_label}  continuation_lr={continuation_lr:.1e}", flush=True)
        prev_actual_k = actual_k
        k = next_k
        t_now = t_end

    print(f"  done in {time.time() - t0_total:.0f}s, {window_idx} windows", flush=True)
    return {
        "t": np.array(t_list), "mae": np.array(mae_list), "k": np.array(k_list),
        "runtime_s": np.array(runtime_list), "continuation_lr": np.array(clr_list),
        "T_ref": np.stack(T_ref_list), "T_pred": np.stack(T_pred_list),
        "loss_total": np.stack(loss_total_list), "loss_pde": np.stack(loss_pde_list),
        "loss_bc": np.stack(loss_bc_list), "loss_end": np.stack(loss_end_list),
        "coords": coords_shared,
    }


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    tm_model, tm_encoder = fit_tm_on_all_data(
        bits_per_feature=8, clauses=60, T=10, s=3.0, epochs=50,
    )

    alg3 = run_with_field_capture(controller="algorithm3", device=device)
    tm = run_with_field_capture(controller="tm_guided", device=device, tm_model=tm_model, tm_encoder=tm_encoder)

    assert np.allclose(alg3["coords"], tm["coords"]), "eval coords should be identical (fixed seed=42)"

    out_path = RESULTS_DIR / "field_snapshots_warmstart_adaptive.npz"
    np.savez(
        out_path,
        coords=alg3["coords"], n_epochs=np.array(TRAIN_KWARGS["n_epochs"]),
        algorithm3_t=alg3["t"], algorithm3_mae=alg3["mae"], algorithm3_k=alg3["k"],
        algorithm3_runtime_s=alg3["runtime_s"], algorithm3_continuation_lr=alg3["continuation_lr"],
        algorithm3_T_ref=alg3["T_ref"], algorithm3_T_pred=alg3["T_pred"],
        algorithm3_loss_total=alg3["loss_total"], algorithm3_loss_pde=alg3["loss_pde"],
        algorithm3_loss_bc=alg3["loss_bc"], algorithm3_loss_end=alg3["loss_end"],
        tm_guided_t=tm["t"], tm_guided_mae=tm["mae"], tm_guided_k=tm["k"],
        tm_guided_runtime_s=tm["runtime_s"], tm_guided_continuation_lr=tm["continuation_lr"],
        tm_guided_T_ref=tm["T_ref"], tm_guided_T_pred=tm["T_pred"],
        tm_guided_loss_total=tm["loss_total"], tm_guided_loss_pde=tm["loss_pde"],
        tm_guided_loss_bc=tm["loss_bc"], tm_guided_loss_end=tm["loss_end"],
    )
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
