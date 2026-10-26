"""
experiments/tm_adaptive_k_rectangle_fenics/single_leap_tm_experiment.py
===========================================================================
TM-gated variant of the single-leap experiment. The original
single_leap_experiment.py trains window 2 (t=1.5s->30s, k~=19, one shot)
with train_to_best(), which decides when to stop by watching the TRUE
mae_C - that requires a live FEM ground-truth evaluation at every slice,
which is not how a deployed controller would work (mae_C is exactly the
thing FEM-anchoring is meant to avoid needing every step).

This script instead gates the SAME retry-in-place loop on the TM
classifier's SAFE/UNSAFE prediction from window DIAGNOSTICS ONLY (PDE
residual, gradient, loss_pde/bc/end, Fo, Bi, phase, k) - no access to
mae_C for the stopping decision, matching exactly how tm_hybrid's
retry_until_safe() gates normal (k<=5) windows in compare_controllers.py.
mae_C is still computed every slice for AUDITING (was TM right?), never
fed to the decision.

Important caveat this experiment is explicitly designed to surface: the TM
classifier was trained ONLY on k=1..5 fixed-k sweep data (feature_logging_
run.py). A single-leap window has k~=19 - this is a genuine
out-of-distribution generalization test for the TM, not just a rerun.

Output: reports/single_leap_tm_{arch}_seed{N}.json per run, plus
reports/single_leap_tm_sweep.json (all runs combined).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_controllers import fit_tm_on_all_data, tm_predict_row
from feature_logging_run import compute_window_diagnostics, phase_of, theta_from_domain
from live_fem_reference import LiveFEMReference

from thermal_pinn.network.pinn import make_pinn
from thermal_pinn.training.trainer import K_THERM, evaluate_window, train_window

DIM = 2
RESOLUTION = 30
T_TOTAL = 30.0
DT_FEM = 1.5
ACCEPT_THRESH_C = 10.0
BASE_EPOCHS = 800
N_EVAL = 2500
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports" / "rectangle"


def run(arch: str, device, model_seed: int, max_total_epochs: int, tm_model, tm_encoder) -> dict:
    domain = LiveFEMReference(resolution=RESOLUTION)
    torch.manual_seed(model_seed)
    model = make_pinn(dim=DIM, arch=arch, device=device)

    L_char = float(np.sqrt(domain.Lx * domain.Ly))
    Bi = domain.h * L_char / K_THERM

    windows_spec = [("anchor", 0.0, DT_FEM), ("single_leap", DT_FEM, T_TOTAL)]
    results = []
    t0_total = time.time()

    for label, t_start, t_end in windows_spec:
        def theta_ic_fn(coords_np, _t=t_start):
            return theta_from_domain(domain, coords_np, _t)

        def theta_end_fn(coords_np, _t=t_end):
            return theta_from_domain(domain, coords_np, _t)

        k_equiv = round((t_end - t_start) / DT_FEM)
        history = []
        total_epochs = 0
        attempt = 0
        cumulative_runtime = 0.0

        while True:
            attempt += 1
            seed = k_equiv if attempt == 1 else k_equiv * 1000 + attempt
            train_info = train_window(
                model=model, domain=domain, t_start=t_start, t_end=t_end,
                theta_ic_fn=theta_ic_fn, theta_end_fn=theta_end_fn, device=device,
                rng_seed=seed, n_domain=1500, n_bc=300, n_epochs=BASE_EPOCHS,
                lr=1e-3, lr_min=1e-5, lbfgs_iters=50, use_end_supervision=True,
            )
            cumulative_runtime += train_info["runtime_s"]
            total_epochs += BASE_EPOCHS
            eval_info = evaluate_window(model=model, domain=domain, t_start=t_start, t_end=t_end,
                                         theta_ic_fn=theta_ic_fn, n_eval=N_EVAL, device=device)
            diag = compute_window_diagnostics(model, domain, t_start, t_end, theta_ic_fn, N_EVAL, device)
            mae = float(eval_info["mae_C"])
            true_label = "SAFE" if mae <= ACCEPT_THRESH_C else "UNSAFE"

            Fo = domain.alpha * (t_end - t_start) / (L_char ** 2)
            row = {
                "arch": arch, "k": k_equiv, "phase": phase_of(t_start), "Fo": float(Fo), "Bi": float(Bi),
                "loss_pde": float(train_info["loss_pde_history"][-1]),
                "loss_bc": float(train_info["loss_bc_history"][-1]),
                "loss_end": float(train_info["loss_end_history"][-1]),
                **diag,
            }
            # TM never sees mae_C - only diagnostics that don't require FEM ground truth.
            tm_pred = tm_predict_row(tm_model, tm_encoder, row)

            history.append({
                "attempt": attempt, "total_epochs": total_epochs, "mae_C": mae,
                "true_label": true_label, "tm_pred": tm_pred,
                "grad_mean": diag["grad_mean"], "pde_residual_mean": diag["pde_residual_mean"],
            })
            print(f"  [{arch}][{label}] attempt={attempt} epochs={total_epochs} MAE={mae:.2f}C "
                  f"true={true_label} TM={tm_pred}", flush=True)

            if tm_pred == "SAFE" or total_epochs >= max_total_epochs:
                break

        eval_info_final = eval_info
        results.append({
            "label": label, "t_start": float(t_start), "t_end": float(t_end), "k_equiv": k_equiv,
            "mae_C": float(eval_info_final["mae_C"]), "l2_rel": float(eval_info_final["l2_rel"]),
            "true_label": history[-1]["true_label"], "tm_pred_final": history[-1]["tm_pred"],
            "tm_was_right": history[-1]["tm_pred"] == history[-1]["true_label"],
            "n_epochs_used": total_epochs, "n_attempts": attempt,
            "runtime_s": cumulative_runtime, "history": history,
            "hit_epoch_ceiling": total_epochs >= max_total_epochs and history[-1]["true_label"] == "UNSAFE",
        })

    return {
        "arch": arch, "domain": "rectangle", "model_seed": model_seed,
        "max_total_epochs": max_total_epochs, "total_s": time.time() - t0_total,
        "windows": results,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archs", nargs="+", default=["bayesian"], choices=["bayesian", "nsga2", "nsga3"])
    p.add_argument("--n-seeds", type=int, default=1)
    p.add_argument("--seed-base", type=int, default=42)
    p.add_argument("--max-total-epochs", type=int, default=40000)
    p.add_argument("--cuda", action="store_true")
    p.add_argument("--device", default=None)
    args = p.parse_args()

    if args.device is not None:
        device = torch.device(args.device)
    elif args.cuda:
        device = torch.device("cuda")
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    seeds = [args.seed_base + i for i in range(args.n_seeds)]
    print(f"Device: {device}  archs: {args.archs}  seeds: {seeds}  "
          f"max_total_epochs: {args.max_total_epochs}", flush=True)

    tm_model, tm_encoder = fit_tm_on_all_data(bits_per_feature=8, clauses=60, T=10, s=3.0, epochs=50)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    all_results = []
    for arch in args.archs:
        for seed in seeds:
            print(f"\n########## arch={arch} seed={seed} ##########", flush=True)
            result = run(arch, device, seed, args.max_total_epochs, tm_model, tm_encoder)
            out_path = REPORTS_DIR / f"single_leap_tm_{arch}_seed{seed}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            all_results.append(result)

    combined_path = REPORTS_DIR / "single_leap_tm_sweep.json"
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved {len(all_results)} runs -> {combined_path}")


if __name__ == "__main__":
    main()
