"""
experiments/tm_adaptive_k_rectangle_fenics/geometry_window1_test.py
=======================================================================
Window-1 cold-start freeze test, generalized to Circle and L-shape (was
only ever run on Rectangle - see memory: "cold-start IC-donması" section).

Root cause recap: window 1's IC is theta_ic=1.0 everywhere (T=T_init, the
max), so ThermalPINN.forward's clamp(theta_ic + tau*delta, 0, 1) zeroes the
gradient wherever delta>=0 - traps ANY architecture in a "frozen at IC"
state. On Rectangle this was confirmed BYTE-IDENTICAL across Bayesian/
NSGA-II (grad_mean=pde_residual_mean=0.0 EXACTLY). The open question this
script answers for Circle/L-shape: does the SAME exact-zero freeze happen,
or does geometry change the picture (e.g. only a slow-but-nonzero
gradient)? This distinction matters because boost_epochs (more training)
only helps the slow-but-nonzero case - it is proven USELESS against an
exact-zero freeze (see "TM-boosted fixed-k sweep bulgusu" in memory).

Trains ONLY window 1 (t=0->1.5s, k=1, base_epochs=800, same TRAIN_KWARGS as
compare_controllers.py) for every (geometry, arch) combination and reports
grad_mean / pde_residual_mean / mae_C - cheap, ~10-20s per combination.

Usage
-----
    cd thermal_pinn/experiments/tm_adaptive_k_rectangle_fenics
    PYTHONPATH=/home/coder/NAS-PINNS1 python3 code/geometry_window1_test.py --cuda
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feature_logging_run import compute_window_diagnostics, theta_from_domain
from live_fem_reference import LiveFEMReference

from thermal_pinn.network.pinn import make_pinn
from thermal_pinn.training.trainer import evaluate_window, train_window

DIM = 2
DT_FEM = 1.5
MODEL_SEED = 42
N_EVAL = 2500
TRAIN_KWARGS = dict(n_domain=1500, n_bc=300, n_epochs=800,
                     lr=1e-3, lr_min=1e-5, lbfgs_iters=50, use_end_supervision=True)
GEOMETRIES = ["rectangle", "circle", "lshape"]
ARCHS = ["bayesian", "nsga2", "nsga3"]
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def run_one(geometry: str, arch: str, device, resolution: int) -> dict:
    domain = LiveFEMReference(geometry=geometry, resolution=resolution)
    torch.manual_seed(MODEL_SEED)
    model = make_pinn(dim=DIM, arch=arch, device=device)

    t_start, t_end = 0.0, DT_FEM

    def theta_ic_fn(coords_np, _t=t_start):
        return theta_from_domain(domain, coords_np, _t)

    def theta_end_fn(coords_np, _t=t_end):
        return theta_from_domain(domain, coords_np, _t)

    train_info = train_window(
        model=model, domain=domain, t_start=t_start, t_end=t_end,
        theta_ic_fn=theta_ic_fn, theta_end_fn=theta_end_fn,
        device=device, rng_seed=1, **TRAIN_KWARGS,
    )
    eval_info = evaluate_window(model=model, domain=domain, t_start=t_start, t_end=t_end,
                                 theta_ic_fn=theta_ic_fn, n_eval=N_EVAL, device=device)
    diag = compute_window_diagnostics(model, domain, t_start, t_end, theta_ic_fn, N_EVAL, device)

    mae = float(eval_info["mae_C"])
    grad_mean = diag["grad_mean"]
    residual_mean = diag["pde_residual_mean"]
    exact_zero = grad_mean == 0.0 and residual_mean == 0.0

    return {
        "geometry": geometry, "arch": arch, "mae_C": mae,
        "grad_mean": grad_mean, "pde_residual_mean": residual_mean,
        "exact_zero_freeze": exact_zero,
        "diagnosis": "TAM DONUK (grad=residual=0.0 exact)" if exact_zero else "canli (sifir degil)",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--geometries", nargs="+", default=GEOMETRIES, choices=GEOMETRIES)
    p.add_argument("--archs", nargs="+", default=ARCHS, choices=ARCHS)
    p.add_argument("--resolution", type=int, default=30)
    p.add_argument("--cuda", action="store_true")
    p.add_argument("--device", default=None)
    args = p.parse_args()

    if args.device is not None:
        device = torch.device(args.device)
    elif args.cuda:
        device = torch.device("cuda")
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}  geometries: {args.geometries}  archs: {args.archs}", flush=True)

    results = []
    for geometry in args.geometries:
        for arch in args.archs:
            print(f"\n=== {geometry} / {arch} ===", flush=True)
            r = run_one(geometry, arch, device, args.resolution)
            print(f"  MAE={r['mae_C']:.2f}C  grad_mean={r['grad_mean']:.6f}  "
                  f"pde_residual_mean={r['pde_residual_mean']:.6f}  -> {r['diagnosis']}", flush=True)
            results.append(r)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "geometry_window1_test.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved -> {out_path}")

    print("\n=== SUMMARY ===")
    for r in results:
        print(f"  {r['geometry']:10s} {r['arch']:10s} {r['diagnosis']}")


if __name__ == "__main__":
    main()
