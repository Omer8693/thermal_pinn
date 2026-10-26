"""
experiments/tm_adaptive_k_rectangle_fenics/field_snapshots.py
=====================================================================
Re-runs the Algorithm 3 and TM-guided adaptive-k loops on Rectangle
(bayesian arch, same model_seed=42 / same LiveFEMReference as
compare_controllers.py) but additionally captures the REAL spatial
field at every window's t_end: the FEM reference values, the PINN
prediction, and the (fixed, seed=42) evaluation coordinates that
evaluate_window() already samples every call.

compare_controllers.py only logged the scalar mae_C/l2_rel per window
- it never saved T_pred/T_ref, so there was no way to draw a real
"FEM reference | PINN prediction | absolute error" field figure (the
fenics_repro/results/*_reference_adaptive.png images are fallback
placeholders: no prediction file was ever supplied, so the "prediction"
panel there is just a copy of the reference field).

Output: results/field_snapshots.npz with, per controller:
    {controller}_t            (n_windows,)        t_end of each window
    {controller}_mae          (n_windows,)        mae_C of each window
    {controller}_k            (n_windows,)        k_used of each window
    {controller}_runtime_s    (n_windows,)        wall-clock training time of each window
    {controller}_T_ref        (n_windows, N_EVAL) FEM reference field
    {controller}_T_pred       (n_windows, N_EVAL) PINN prediction field
    {controller}_loss_total   (n_windows, n_epochs) total loss per epoch, all windows
    {controller}_loss_pde     (n_windows, n_epochs) PDE residual loss per epoch
    {controller}_loss_bc      (n_windows, n_epochs) Robin BC loss per epoch
    {controller}_loss_end     (n_windows, n_epochs) FEM end-supervision loss per epoch
    coords                    (N_EVAL, 2)         shared eval points (fixed rng seed=42)

Every window uses the same n_epochs (TRAIN_KWARGS["n_epochs"], default 800),
so the per-window loss histories stack cleanly into 2D arrays - this is what
was missing before: previously only the FINAL loss value of each window was
kept (compare_controllers.py's `row["loss_pde"]` etc.), so there was no way
to plot a loss-vs-epoch curve or know how many epochs were actually run
without re-training from scratch.
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
from hybrid_controller import HybridState, decide as hybrid_decide, retry_until_safe
from live_fem_reference import LiveFEMReference

from thermal_pinn.network.pinn import make_pinn
from thermal_pinn.training.trainer import K_THERM, evaluate_window, train_window

DIM = 2
MODEL_SEED = 42
RESOLUTION = 30
N_EVAL = 2500
RESULTS_DIR = Path(__file__).resolve().parent.parent / "npz"


def run_with_field_capture(*, controller: str, arch: str, device, tm_model=None, tm_encoder=None,
                            boost_epochs: int = 0, boost_windows: int = 0, geometry: str = "rectangle"):
    """boost_epochs/boost_windows: give the first `boost_windows` windows a
    bigger n_epochs budget (0 = disabled, i.e. every window uses
    TRAIN_KWARGS["n_epochs"] as before). Root cause + evidence: window 1's
    IC is uniformly theta_ic=1.0 (T=540C, the max), so ThermalPINN.forward's
    clamp(theta_ic + tau*delta, 0, 1) zeroes the gradient wherever delta>=0
    - this traps ANY architecture in a "frozen at IC" state for window 1
    (verified byte-identical between bayesian/nsga2 in both this
    experiment's live-FEniCS capture and the older raw_runs/*_k1_*.json
    fixed-k sweep: grad_mean=pde_residual_mean=0.0 exactly, MAE=8.95C to
    the last digit). Bayesian's larger capacity (5x151 ReLU) escapes and
    recovers by window 2; nsga2 (3x153 tanh) and nsga3 (3x75 tanh) take
    several more windows, causing the extra UNSAFE (>10C) windows seen
    with nsga2/nsga3 that bayesian does not have. Testing
    boost_epochs=6400 (8x) for the first 3 windows eliminated ALL unsafe
    windows for both nsga2 and nsga3, both controllers (see
    tm_adaptive_k_rectangle_experiment.md memory for the before/after
    table) - default here stays 0 (off) so bayesian's existing figures are
    unaffected; pass --boost-epochs/--boost-windows to enable."""
    domain = LiveFEMReference(geometry=geometry, resolution=RESOLUTION)
    torch.manual_seed(MODEL_SEED)
    model = make_pinn(dim=DIM, arch=arch, device=device)

    L_char = float(np.sqrt(domain.Lx * domain.Ly))
    Bi = domain.h * L_char / K_THERM

    k = K_MIN
    t_now = 0.0
    window_idx = 0
    t_list, mae_list, k_list, runtime_list = [], [], [], []
    T_ref_list, T_pred_list = [], []
    loss_total_list, loss_pde_list, loss_bc_list, loss_end_list = [], [], [], []
    coords_shared = None
    t0_total = time.time()
    hybrid_state = HybridState()
    prev_k_hybrid, prev_mae_hybrid = None, None
    base_n_epochs = TRAIN_KWARGS["n_epochs"]
    train_kwargs = dict(TRAIN_KWARGS)

    print(f"\n=== {controller} (field capture) ===", flush=True)
    while t_now < T_TOTAL - 1e-6:
        dt_window = k * DT_FEM
        t_end = min(t_now + dt_window, T_TOTAL)
        actual_k = round((t_end - t_now) / DT_FEM)
        window_idx += 1
        t_start = t_now

        def theta_ic_fn(coords_np, _t=t_start):
            return theta_from_domain(domain, coords_np, _t)

        def theta_end_fn(coords_np, _t=t_end):
            return theta_from_domain(domain, coords_np, _t)

        window_kwargs = dict(train_kwargs)
        if window_idx <= boost_windows:
            window_kwargs["n_epochs"] = boost_epochs

        if controller == "tm_hybrid":
            attempt = [0]
            cumulative_runtime = [0.0]

            def train_epochs_fn(n_epochs, _attempt=attempt, _rt=cumulative_runtime):
                _attempt[0] += 1
                seed = window_idx if _attempt[0] == 1 else window_idx * 1000 + _attempt[0]
                info = train_window(
                    model=model, domain=domain, t_start=t_start, t_end=t_end,
                    theta_ic_fn=theta_ic_fn, theta_end_fn=theta_end_fn,
                    device=device, rng_seed=seed,
                    **{**window_kwargs, "n_epochs": n_epochs},
                )
                _rt[0] += info["runtime_s"]
                return info

            def eval_fn():
                return evaluate_window(
                    model=model, domain=domain, t_start=t_start, t_end=t_end,
                    theta_ic_fn=theta_ic_fn, n_eval=N_EVAL, device=device,
                )

            retry_result = retry_until_safe(
                train_epochs_fn=train_epochs_fn, eval_fn=eval_fn,
                base_epochs=window_kwargs["n_epochs"], accept_thresh_C=ACCEPT_THRESH_C,
            )
            train_info = {**retry_result.train_info, "runtime_s": cumulative_runtime[0]}
            eval_info = retry_result.eval_info
        else:
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
        if coords_shared is None:
            coords_shared = eval_info["coords"]
        t_list.append(t_end)
        mae_list.append(mae)
        k_list.append(actual_k)
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
        row = {"arch": arch, "k": actual_k, "phase": phase_of(t_start),
               "Fo": float(Fo), "Bi": float(Bi), **final_loss, **diag}

        prev_k = actual_k
        boost_next_epochs = None
        if controller == "algorithm3":
            if mae < THRESH_UP and prev_k < K_MAX_:
                next_k = prev_k + 1
            elif mae > THRESH_DOWN and prev_k > K_MIN:
                next_k = prev_k - 1
            else:
                next_k = prev_k
        elif controller == "tm_guided":
            tm_pred = tm_predict_row(tm_model, tm_encoder, row)
            next_k = max(K_MIN, prev_k - 1) if tm_pred == "UNSAFE" else min(K_MAX_, prev_k + 1)
        else:  # tm_hybrid
            tm_pred = tm_predict_row(tm_model, tm_encoder, row)
            ref_k = prev_k if prev_k_hybrid is None else prev_k_hybrid
            ref_mae = mae if prev_mae_hybrid is None else prev_mae_hybrid
            decision = hybrid_decide(
                prev_k=ref_k, prev_mae=ref_mae, mae=mae, actual_k=actual_k,
                tm_pred=tm_pred, row=row, state=hybrid_state,
                k_min=K_MIN, k_max=K_MAX_, base_epochs=base_n_epochs, geometry=geometry,
            )
            next_k = decision.next_k
            boost_next_epochs = decision.epochs_for_next_window
            prev_k_hybrid, prev_mae_hybrid = actual_k, mae

        if boost_next_epochs is not None:
            train_kwargs = dict(train_kwargs, n_epochs=boost_next_epochs)
        elif controller == "tm_hybrid" and train_kwargs["n_epochs"] != base_n_epochs:
            train_kwargs = dict(train_kwargs, n_epochs=base_n_epochs)

        print(f"  [{window_idx:>2}] t={t_end:.1f}s  k={actual_k}  MAE={mae:.2f}C  true={true_label}", flush=True)
        k = next_k
        t_now = t_end

    print(f"  done in {time.time() - t0_total:.0f}s, {window_idx} windows", flush=True)

    def pad_stack(arrs):
        # Boosted windows run more epochs than the rest, so the per-window
        # loss histories are ragged - pad the shorter ones with NaN (from
        # the end) so they still stack into one 2D array. Plot code should
        # skip NaNs (matplotlib does this by default).
        max_len = max(a.shape[0] for a in arrs)
        return np.stack([np.pad(a, (0, max_len - a.shape[0]), constant_values=np.nan) for a in arrs])

    return {
        "t": np.array(t_list), "mae": np.array(mae_list), "k": np.array(k_list),
        "runtime_s": np.array(runtime_list),
        "T_ref": np.stack(T_ref_list), "T_pred": np.stack(T_pred_list),
        "loss_total": pad_stack(loss_total_list), "loss_pde": pad_stack(loss_pde_list),
        "loss_bc": pad_stack(loss_bc_list), "loss_end": pad_stack(loss_end_list),
        "coords": coords_shared,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry", default="rectangle", choices=["rectangle", "circle", "lshape"])
    parser.add_argument("--arch", default="bayesian", choices=["bayesian", "nsga2", "nsga3"])
    parser.add_argument("--boost-epochs", type=int, default=0,
                         help="n_epochs for the first --boost-windows windows (0 = disabled). "
                              "6400 fixed all NSGA-II/NSGA-III cold-start safety violations - see memory.")
    parser.add_argument("--boost-windows", type=int, default=0,
                         help="How many early windows get the boosted epoch budget.")
    parser.add_argument("--tag", default="",
                         help="Extra filename suffix (e.g. 'baseline800') so this run does not "
                              "overwrite the arch's official field_snapshots{_arch}.npz.")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}  arch: {args.arch}  boost_epochs={args.boost_epochs}  "
          f"boost_windows={args.boost_windows}")

    tm_model, tm_encoder = fit_tm_on_all_data(
        bits_per_feature=8, clauses=60, T=10, s=3.0, epochs=50, geometry=args.geometry,
    )

    alg3 = run_with_field_capture(controller="algorithm3", arch=args.arch, device=device,
                                   boost_epochs=args.boost_epochs, boost_windows=args.boost_windows,
                                   geometry=args.geometry)
    tm = run_with_field_capture(controller="tm_guided", arch=args.arch, device=device,
                                 tm_model=tm_model, tm_encoder=tm_encoder,
                                 boost_epochs=args.boost_epochs, boost_windows=args.boost_windows,
                                 geometry=args.geometry)
    hybrid = run_with_field_capture(controller="tm_hybrid", arch=args.arch, device=device,
                                     tm_model=tm_model, tm_encoder=tm_encoder,
                                     boost_epochs=args.boost_epochs, boost_windows=args.boost_windows,
                                     geometry=args.geometry)

    assert np.allclose(alg3["coords"], tm["coords"]), "eval coords should be identical (fixed seed=42)"
    assert np.allclose(alg3["coords"], hybrid["coords"]), "eval coords should be identical (fixed seed=42)"

    # rectangle keeps the original flat npz/ layout (backward compat);
    # circle/lshape get their own npz/{geometry}/ subfolder.
    out_dir = RESULTS_DIR / args.geometry
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.arch == "bayesian" else f"_{args.arch}"
    tag_suffix = f"_{args.tag}" if args.tag else ""
    out_path = out_dir / f"field_snapshots{suffix}{tag_suffix}.npz"
    np.savez(
        out_path,
        coords=alg3["coords"], n_epochs=np.array(TRAIN_KWARGS["n_epochs"]),
        boost_epochs=np.array(args.boost_epochs), boost_windows=np.array(args.boost_windows),
        algorithm3_t=alg3["t"], algorithm3_mae=alg3["mae"], algorithm3_k=alg3["k"],
        algorithm3_runtime_s=alg3["runtime_s"],
        algorithm3_T_ref=alg3["T_ref"], algorithm3_T_pred=alg3["T_pred"],
        algorithm3_loss_total=alg3["loss_total"], algorithm3_loss_pde=alg3["loss_pde"],
        algorithm3_loss_bc=alg3["loss_bc"], algorithm3_loss_end=alg3["loss_end"],
        tm_guided_t=tm["t"], tm_guided_mae=tm["mae"], tm_guided_k=tm["k"],
        tm_guided_runtime_s=tm["runtime_s"],
        tm_guided_T_ref=tm["T_ref"], tm_guided_T_pred=tm["T_pred"],
        tm_guided_loss_total=tm["loss_total"], tm_guided_loss_pde=tm["loss_pde"],
        tm_guided_loss_bc=tm["loss_bc"], tm_guided_loss_end=tm["loss_end"],
        tm_hybrid_t=hybrid["t"], tm_hybrid_mae=hybrid["mae"], tm_hybrid_k=hybrid["k"],
        tm_hybrid_runtime_s=hybrid["runtime_s"],
        tm_hybrid_T_ref=hybrid["T_ref"], tm_hybrid_T_pred=hybrid["T_pred"],
        tm_hybrid_loss_total=hybrid["loss_total"], tm_hybrid_loss_pde=hybrid["loss_pde"],
        tm_hybrid_loss_bc=hybrid["loss_bc"], tm_hybrid_loss_end=hybrid["loss_end"],
    )
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
