"""
experiments/tm_adaptive_k_rectangle_fenics/single_leap_experiment.py
=====================================================================
Most aggressive possible test of the adaptive-k idea: instead of
stepping k by +-1 window-by-window (algorithm3/tm_guided/tm_hybrid all
do this), window 1 trains normally against the real FEM reference
(k=1, t=0->1.5s, base_epochs) - exactly like every other controller -
then window 2 skips ALL intermediate steps and jumps DIRECTLY to
t_end=T_TOTAL (the rest of the whole 30s cooldown in one window,
k~=19), using hybrid_controller.train_to_best() to keep training until
the result PLATEAUS (no further improvement), not just until it first
crosses the 10C safety threshold - an early test used
retry_until_safe() (stop at first SAFE) and got a leap MAE of 9.94C,
uncomfortably close to the threshold; train_to_best answers "how good
can this window actually get" instead, checkpointing the model's best
weights along the way so the final model matches the best result even
if further training made things worse afterward.

This is explicitly a one-off exploratory test (2 windows total, not a
sweep) - see the user's "Fikir 3" request in
tm_adaptive_k_rectangle_experiment.md memory: "starting from window 1
with the FEM reference like the others, skip all the other steps in
one go using TM, and let it try as much epoch as is actually needed
after FEM". Because a k~=19 leap is far more extreme than anything the
proven 6400-epoch ceiling was validated against, this script uses its
own (much higher, configurable) epoch ceiling rather than
hybrid_controller.MAX_TOTAL_EPOCHS - if it never converges even with a
generous budget, that is itself the answer (this single-window jump is
too aggressive for a 30s cooldown), not a bug to work around.

Usage
-----
    cd thermal_pinn/experiments/tm_adaptive_k_rectangle_fenics
    PYTHONPATH=/home/coder/NAS-PINNS1 python3 code/single_leap_experiment.py \\
        --arch bayesian --cuda
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
from feature_logging_run import compute_window_diagnostics, phase_of, theta_from_domain
from hybrid_controller import train_to_best
from live_fem_reference import LiveFEMReference

from thermal_pinn.network.pinn import make_pinn
from thermal_pinn.training.trainer import K_THERM, evaluate_window, train_window

DIM = 2
T_TOTAL = 30.0
DT_FEM = 1.5
ACCEPT_THRESH_C = 10.0
RESOLUTION = 30
N_EVAL = 2500
RETRY_INCREMENT = 800
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports" / "rectangle"


def run(arch: str, device, model_seed: int, base_epochs: int, max_total_epochs: int,
        lbfgs_iters: int, patience: int) -> dict:
    domain = LiveFEMReference(resolution=RESOLUTION)
    torch.manual_seed(model_seed)
    model = make_pinn(dim=DIM, arch=arch, device=device)

    L_char = float(np.sqrt(domain.Lx * domain.Ly))
    Bi = domain.h * L_char / K_THERM

    windows_spec = [
        ("anchor", 0.0, DT_FEM),           # window 1: normal, k=1, FEM-anchored - same as every other controller
        ("single_leap", DT_FEM, T_TOTAL),  # window 2: skip straight to the end, k~=19
    ]

    results = []
    t0_total = time.time()

    for label, t_start, t_end in windows_spec:
        k_equiv = round((t_end - t_start) / DT_FEM)

        def theta_ic_fn(coords_np, _t=t_start):
            return theta_from_domain(domain, coords_np, _t)

        def theta_end_fn(coords_np, _t=t_end):
            return theta_from_domain(domain, coords_np, _t)

        attempt = [0]
        cumulative_runtime = [0.0]

        def train_epochs_fn(n_epochs, _attempt=attempt, _rt=cumulative_runtime):
            _attempt[0] += 1
            seed = k_equiv if _attempt[0] == 1 else k_equiv * 1000 + _attempt[0]
            info = train_window(
                model=model, domain=domain, t_start=t_start, t_end=t_end,
                theta_ic_fn=theta_ic_fn, theta_end_fn=theta_end_fn, device=device,
                rng_seed=seed,
                n_domain=1500, n_bc=300, n_epochs=n_epochs,
                lr=1e-3, lr_min=1e-5, lbfgs_iters=lbfgs_iters, use_end_supervision=True,
            )
            _rt[0] += info["runtime_s"]
            return info

        def eval_fn():
            return evaluate_window(
                model=model, domain=domain, t_start=t_start, t_end=t_end,
                theta_ic_fn=theta_ic_fn, n_eval=N_EVAL, device=device,
            )

        def get_state_fn():
            return {k: v.clone() for k, v in model.state_dict().items()}

        def set_state_fn(state):
            model.load_state_dict(state)

        print(f"\n=== window [{label}] t={t_start:.1f}->{t_end:.1f}s (k~={k_equiv}) ===", flush=True)
        best_result = train_to_best(
            train_epochs_fn=train_epochs_fn, eval_fn=eval_fn,
            get_state_fn=get_state_fn, set_state_fn=set_state_fn,
            base_epochs=base_epochs, increment=RETRY_INCREMENT, max_total_epochs=max_total_epochs,
            patience=patience,
        )
        eval_info = best_result.eval_info
        diag = compute_window_diagnostics(model, domain, t_start, t_end, theta_ic_fn, N_EVAL, device)
        mae = float(eval_info["mae_C"])
        true_label = "SAFE" if mae <= ACCEPT_THRESH_C else "UNSAFE"

        print(
            f"  MAE={mae:.2f}C  {true_label}  best_at_epoch={best_result.best_epochs}  "
            f"epochs_tried={best_result.epochs_tried}  runtime={cumulative_runtime[0]:.0f}s  "
            f"grad_mean={diag['grad_mean']:.2e}", flush=True,
        )

        results.append({
            "label": label, "t_start": float(t_start), "t_end": float(t_end), "k_equiv": k_equiv,
            "mae_C": mae, "l2_rel": float(eval_info["l2_rel"]), "true_label": true_label,
            "n_epochs_used": best_result.best_epochs, "epochs_tried": best_result.epochs_tried,
            "runtime_s": float(cumulative_runtime[0]),
            "hit_epoch_ceiling": best_result.epochs_tried >= max_total_epochs and true_label == "UNSAFE",
            **diag,
        })

    return {
        "arch": arch, "domain": "rectangle", "model_seed": model_seed,
        "base_epochs": base_epochs, "max_total_epochs": max_total_epochs,
        "total_s": time.time() - t0_total, "windows": results,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archs", nargs="+", default=["bayesian"], choices=["bayesian", "nsga2", "nsga3"])
    p.add_argument("--n-seeds", type=int, default=1,
                    help="Repeat with this many model seeds (42, 43, 42+n_seeds-1, ...) per "
                         "architecture, since a single seed's result (esp. one this close to "
                         "the 10C threshold) can be luck - see memory.")
    p.add_argument("--seed-base", type=int, default=42)
    p.add_argument("--base-epochs", type=int, default=800)
    p.add_argument("--max-total-epochs", type=int, default=20000,
                    help="Epoch ceiling for the single-leap window - deliberately much higher "
                         "than the 6400 proven for a normal k<=5 window, since a k~=19 leap is "
                         "far more extreme; if it still doesn't converge here, that's the answer.")
    p.add_argument("--lbfgs-iters", type=int, default=50)
    p.add_argument("--patience", type=int, default=3,
                    help="train_to_best plateau patience (consecutive no-improvement slices "
                         "before stopping) - default matches hybrid_controller.PLATEAU_PATIENCE. "
                         "Raise this to test whether a low patience is cutting training short "
                         "before a true asymptote (see Bayesian single-leap investigation).")
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

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    patience_tag = f"_patience{args.patience}" if args.patience != 3 else ""
    all_results = []
    for arch in args.archs:
        for seed in seeds:
            print(f"\n########## arch={arch} seed={seed} ##########", flush=True)
            result = run(arch, device, seed, args.base_epochs,
                         args.max_total_epochs, args.lbfgs_iters, args.patience)
            out_path = REPORTS_DIR / f"single_leap_{arch}_seed{seed}{patience_tag}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            all_results.append(result)

    combined_path = REPORTS_DIR / f"single_leap_sweep{patience_tag}.json"
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n=== SWEEP SUMMARY ({len(all_results)} runs) ===")
    print(f"{'arch':<10}{'seed':<6}{'anchor_MAE':<12}{'anchor_frozen':<15}"
          f"{'leap_MAE':<10}{'leap_label':<8}{'best_ep':<10}{'tried_ep':<10}")
    for result in all_results:
        anchor, leap = result["windows"][0], result["windows"][1]
        frozen = "yes" if anchor["grad_mean"] == 0.0 else "no"
        print(f"{result['arch']:<10}{result['model_seed']:<6}{anchor['mae_C']:<12.2f}{frozen:<15}"
              f"{leap['mae_C']:<10.2f}{leap['true_label']:<8}{leap['n_epochs_used']:<10}{leap['epochs_tried']:<10}")

    n_safe = sum(1 for r in all_results if r["windows"][1]["true_label"] == "SAFE")
    print(f"\nLeap window SAFE in {n_safe}/{len(all_results)} runs.")
    print(f"Saved per-run files + combined -> {combined_path}")


if __name__ == "__main__":
    main()
