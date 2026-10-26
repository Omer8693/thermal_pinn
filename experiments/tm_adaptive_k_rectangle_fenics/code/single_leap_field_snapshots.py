"""
experiments/tm_adaptive_k_rectangle_fenics/single_leap_field_snapshots.py
=============================================================================
Re-runs the single-leap experiment (window 1: normal FEM-anchored k=1,
t=0->1.5s; window 2: skip straight to t=30s, k~=19) for one representative
seed per architecture, capturing the REAL spatial field (FEM reference,
PINN prediction, shared eval coords) at both window boundaries via
evaluate_window()'s T_ref/T_pred/coords output - same technique as
field_snapshots.py uses for compare_controllers.py.

Bayesian uses patience=10 (the confirmatory setting proven identical to
patience=3 - see memory) so this matches the authoritative single_leap
result; NSGA-II/III use patience=3 (their original sweep never hit the
epoch ceiling, already fully converged).

Output: npz/single_leap_field_snapshots.npz with, per architecture:
    {arch}_t            (2,)          t_end of [anchor, leap]
    {arch}_mae           (2,)          mae_C of [anchor, leap]
    {arch}_T_ref         (2, N_EVAL)   FEM reference field
    {arch}_T_pred        (2, N_EVAL)   PINN prediction field
    coords                (N_EVAL, 2)  shared eval points (fixed rng seed=42
                                        inside evaluate_window, identical
                                        across architectures/windows)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feature_logging_run import theta_from_domain
from hybrid_controller import train_to_best
from live_fem_reference import LiveFEMReference

from thermal_pinn.network.pinn import make_pinn
from thermal_pinn.training.trainer import evaluate_window, train_window

DIM = 2
MODEL_SEED = 42
RESOLUTION = 30
T_TOTAL = 30.0
DT_FEM = 1.5
N_EVAL = 2500
RETRY_INCREMENT = 800
RESULTS_DIR = Path(__file__).resolve().parent.parent / "npz" / "rectangle"

ARCH_SETTINGS = {
    "bayesian": dict(patience=10, max_total_epochs=40000),
    "nsga2": dict(patience=3, max_total_epochs=20000),
    "nsga3": dict(patience=3, max_total_epochs=20000),
}


def run(arch: str, device) -> dict:
    domain = LiveFEMReference(resolution=RESOLUTION)
    torch.manual_seed(MODEL_SEED)
    model = make_pinn(dim=DIM, arch=arch, device=device)
    settings = ARCH_SETTINGS[arch]

    windows_spec = [("anchor", 0.0, DT_FEM), ("single_leap", DT_FEM, T_TOTAL)]
    t_list, mae_list, T_ref_list, T_pred_list = [], [], [], []
    coords_shared = None
    t0_total = time.time()

    for label, t_start, t_end in windows_spec:
        def theta_ic_fn(coords_np, _t=t_start):
            return theta_from_domain(domain, coords_np, _t)

        def theta_end_fn(coords_np, _t=t_end):
            return theta_from_domain(domain, coords_np, _t)

        k_equiv = round((t_end - t_start) / DT_FEM)
        attempt = [0]

        def train_epochs_fn(n_epochs, _attempt=attempt):
            _attempt[0] += 1
            seed = k_equiv if _attempt[0] == 1 else k_equiv * 1000 + _attempt[0]
            return train_window(
                model=model, domain=domain, t_start=t_start, t_end=t_end,
                theta_ic_fn=theta_ic_fn, theta_end_fn=theta_end_fn, device=device,
                rng_seed=seed, n_domain=1500, n_bc=300, n_epochs=n_epochs,
                lr=1e-3, lr_min=1e-5, lbfgs_iters=50, use_end_supervision=True,
            )

        def eval_fn():
            return evaluate_window(model=model, domain=domain, t_start=t_start, t_end=t_end,
                                    theta_ic_fn=theta_ic_fn, n_eval=N_EVAL, device=device)

        def get_state_fn():
            return {k: v.clone() for k, v in model.state_dict().items()}

        def set_state_fn(state):
            model.load_state_dict(state)

        print(f"  [{arch}] window [{label}] t={t_start:.1f}->{t_end:.1f}s (k~={k_equiv})", flush=True)
        best_result = train_to_best(
            train_epochs_fn=train_epochs_fn, eval_fn=eval_fn,
            get_state_fn=get_state_fn, set_state_fn=set_state_fn,
            base_epochs=800, increment=RETRY_INCREMENT,
            max_total_epochs=settings["max_total_epochs"], patience=settings["patience"],
        )
        eval_info = best_result.eval_info
        mae = float(eval_info["mae_C"])
        if coords_shared is None:
            coords_shared = eval_info["coords"]
        t_list.append(t_end)
        mae_list.append(mae)
        T_ref_list.append(eval_info["T_ref"])
        T_pred_list.append(eval_info["T_pred"])
        print(f"    MAE={mae:.2f}C  best_epoch={best_result.best_epochs}", flush=True)

    print(f"  [{arch}] done in {time.time() - t0_total:.0f}s", flush=True)
    return {
        "t": np.array(t_list), "mae": np.array(mae_list),
        "T_ref": np.stack(T_ref_list), "T_pred": np.stack(T_pred_list),
        "coords": coords_shared,
    }


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}  seed: {MODEL_SEED}")

    results = {}
    for arch in ("bayesian", "nsga2", "nsga3"):
        results[arch] = run(arch, device)

    for arch in ("nsga2", "nsga3"):
        assert np.allclose(results["bayesian"]["coords"], results[arch]["coords"]), \
            "eval coords should be identical across archs (fixed seed=42 inside evaluate_window)"

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "single_leap_field_snapshots.npz"
    save_kwargs = {"coords": results["bayesian"]["coords"]}
    for arch in ("bayesian", "nsga2", "nsga3"):
        save_kwargs[f"{arch}_t"] = results[arch]["t"]
        save_kwargs[f"{arch}_mae"] = results[arch]["mae"]
        save_kwargs[f"{arch}_T_ref"] = results[arch]["T_ref"]
        save_kwargs[f"{arch}_T_pred"] = results[arch]["T_pred"]
    np.savez(out_path, **save_kwargs)
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
