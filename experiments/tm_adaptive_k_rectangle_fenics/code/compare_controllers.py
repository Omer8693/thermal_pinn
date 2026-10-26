"""
experiments/tm_adaptive_k_rectangle_fenics/compare_controllers.py
=====================================================================
Runs the ORIGINAL threshold-based Algorithm 3 (train_adaptive_k.py's
logic: k_init=1, thresh_up=2.0C, thresh_down=5.0C, single step per
window) and the NEW TM-guided controller side by side, on the same
Rectangle domain, same architecture (bayesian), same live-FEniCS FEM
reference, same initial network weights (model_seed) - so the only
difference between the two runs is which decision function chooses k.

TM-guided controller
---------------------
Same step-wise structure as Algorithm 3 (k moves by +-1 per window,
never jumps): after training window i at k_i, the FEM-free diagnostics
already computed for that window (PDE residual, gradient, delta_T, Fo,
Bi, phase, loss_pde/bc/end - NOT the measured mae_C) are fed to the TM
classifier trained in train_tm.py. If TM says SAFE -> try k+1 next
window; if UNSAFE -> drop to k-1. mae_C is still computed (it is a free
byproduct of the FEM anchor call every window already needs for its
end-supervision loss - see module docstring discussion in the report)
and logged for comparison/audit, but the CONTROLLER never looks at it -
only at the TM's binary decision.

Usage
-----
    cd thermal_pinn/experiments/tm_adaptive_k_rectangle_fenics
    python3 extract_features.py           # if not already done
    python3 compare_controllers.py --cuda
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
from binarize import ThermometerEncoder, encode_label
from extract_features import load_raw_runs, to_dataframe
from feature_logging_run import compute_window_diagnostics, phase_of, theta_from_domain
from hybrid_controller import HybridState, decide as hybrid_decide, retry_until_safe
from live_fem_reference import LiveFEMReference

from thermal_pinn.network.pinn import make_pinn
from thermal_pinn.training.trainer import K_THERM, evaluate_window, train_window
from tmu.models.classification.vanilla_classifier import TMClassifier

DIM = 2
T_TOTAL = 30.0
DT_FEM = 1.5
ACCEPT_THRESH_C = 10.0

K_MIN, K_MAX_ = 1, 5
THRESH_UP, THRESH_DOWN = 2.0, 5.0  # Algorithm 3's own parameters

TRAIN_KWARGS = {
    "n_domain": 1500, "n_bc": 300, "n_epochs": 800,
    "lr": 1e-3, "lr_min": 1e-5, "lbfgs_iters": 50, "use_end_supervision": True,
}

RESULTS_DIR = Path(__file__).resolve().parent.parent / "reports"
RAW_RUNS_DIR = Path(__file__).resolve().parent.parent / "raw_runs"
MODEL_CHECKPOINTS_DIR = Path(__file__).resolve().parent.parent / "checkpoints"


def fit_tm_on_all_data(bits_per_feature: int, clauses: int, T: int, s: float, epochs: int,
                        geometry: str = "rectangle"):
    """Train the TM on ALL available (k, window) rows - not held out - since
    this is the model that will actually drive the deployed controller.
    geometry picks which raw_runs/{geometry}/ subfolder to train on (see
    "Ortak kod + geometriye göre ayrı sonuç klasörleri" decision, 2026-09-15
    memory) - a TM trained on the wrong geometry's Fo/Bi/loss statistics
    would silently mismatch."""
    raw_dir = RAW_RUNS_DIR / geometry
    df = to_dataframe(load_raw_runs(raw_dir=raw_dir))
    encoder = ThermometerEncoder(n_bits=bits_per_feature).fit(df)
    X = encoder.transform(df)
    Y = encode_label(df["label"])
    model = TMClassifier(number_of_clauses=clauses, T=T, s=s, platform="CPU", weighted_clauses=True)
    for _ in range(epochs):
        model.fit(X, Y)
    train_acc = float(np.mean(model.predict(X) == Y))
    print(f"[TM] trained on all {len(df)} rows, final train_acc={train_acc:.3f}")
    return model, encoder


def tm_predict_row(model: TMClassifier, encoder: ThermometerEncoder, row: dict) -> str:
    import pandas as pd
    df_row = pd.DataFrame([row])
    X = encoder.transform(df_row)
    pred = model.predict(X)[0]
    return "UNSAFE" if pred == 1 else "SAFE"


def run_window_loop(*, controller: str, arch: str, device, resolution, model_seed, train_kwargs,
                     n_eval, tm_model=None, tm_encoder=None, verbose=True, k_max: int | None = None,
                     geometry: str = "rectangle"):
    domain = LiveFEMReference(geometry=geometry, resolution=resolution)
    torch.manual_seed(model_seed)
    model = make_pinn(dim=DIM, arch=arch, device=device)

    L_char = float(np.sqrt(domain.Lx * domain.Ly))
    Bi = domain.h * L_char / K_THERM
    k_max = K_MAX_ if k_max is None else k_max
    base_n_epochs = train_kwargs["n_epochs"]  # captured before any boost mutation below

    k = K_MIN
    t_now = 0.0
    window_idx = 0
    window_results = []
    t0_total = time.time()
    hybrid_state = HybridState()
    prev_k, prev_mae = None, None

    if verbose:
        print(f"\n=== {controller} ===", flush=True)

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

        retry_count, retry_total_epochs = 0, train_kwargs["n_epochs"]
        if controller == "tm_hybrid":
            # Reactive fix for THIS window (see hybrid_controller module
            # docstring, mechanism 1): keep training in place, re-evaluating
            # after each RETRY_INCREMENT-epoch slice, until SAFE or the
            # ceiling is hit - directly fixes UNSAFE windows instead of only
            # preventing later windows from also failing.
            attempt = [0]
            cumulative_runtime = [0.0]

            def train_epochs_fn(n_epochs, _attempt=attempt, _rt=cumulative_runtime):
                _attempt[0] += 1
                # First attempt uses the SAME seed as algorithm3/tm_guided's
                # single call for this window (rng_seed=window_idx) so a
                # 0-retry window is seed-identical to the other two
                # controllers - any difference is then attributable only to
                # the epoch budget (boost-next), not random collocation-point
                # sampling luck. Only actual retries get a distinct seed.
                seed = window_idx if _attempt[0] == 1 else window_idx * 1000 + _attempt[0]
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
            retry_count, retry_total_epochs = retry_result.retry_count, retry_result.total_epochs
            train_info = {**train_info, "runtime_s": cumulative_runtime[0]}  # sum across all attempts
        else:
            train_info = train_window(
                model=model, domain=domain, t_start=t_start, t_end=t_end,
                theta_ic_fn=theta_ic_fn, theta_end_fn=theta_end_fn,
                device=device, rng_seed=window_idx, **train_kwargs,
            )
            eval_info = evaluate_window(
                model=model, domain=domain, t_start=t_start, t_end=t_end,
                theta_ic_fn=theta_ic_fn, n_eval=n_eval, device=device,
            )
        diag = compute_window_diagnostics(model, domain, t_start, t_end, theta_ic_fn, n_eval, device)

        mae = float(eval_info["mae_C"])
        Fo = domain.alpha * (t_end - t_start) / (L_char ** 2)
        true_label = "SAFE" if mae <= ACCEPT_THRESH_C else "UNSAFE"
        final_loss = {
            "loss_pde": float(train_info["loss_pde_history"][-1]),
            "loss_bc": float(train_info["loss_bc_history"][-1]),
            "loss_end": float(train_info["loss_end_history"][-1]),
        }

        row = {
            "arch": arch, "k": actual_k, "phase": phase_of(t_start),
            "Fo": float(Fo), "Bi": float(Bi), **final_loss, **diag,
        }

        prev_k_step = actual_k
        risk_flag, diagnosis, boost_next_epochs = False, None, None
        if controller == "algorithm3":
            if mae < THRESH_UP and prev_k_step < k_max:
                next_k = prev_k_step + 1
            elif mae > THRESH_DOWN and prev_k_step > K_MIN:
                next_k = prev_k_step - 1
            else:
                next_k = prev_k_step
            decision_reason = (
                f"MAE={mae:.2f}C vs thresh_up={THRESH_UP} / thresh_down={THRESH_DOWN}"
            )
            tm_pred = None
        elif controller == "tm_guided":
            tm_pred = tm_predict_row(tm_model, tm_encoder, row)
            if tm_pred == "UNSAFE":
                next_k = max(K_MIN, prev_k_step - 1)
            else:
                next_k = min(k_max, prev_k_step + 1)
            decision_reason = f"TM predicted {tm_pred} (true={true_label})"
        else:  # tm_hybrid
            tm_pred = tm_predict_row(tm_model, tm_encoder, row)
            ref_k = prev_k_step if prev_k is None else prev_k
            ref_mae = mae if prev_mae is None else prev_mae
            decision = hybrid_decide(
                prev_k=ref_k, prev_mae=ref_mae, mae=mae, actual_k=actual_k,
                tm_pred=tm_pred, row=row, state=hybrid_state,
                k_min=K_MIN, k_max=k_max, base_epochs=base_n_epochs, geometry=geometry,
            )
            next_k = decision.next_k
            decision_reason = decision.reason
            risk_flag = decision.risk_flag
            diagnosis = decision.diagnosis
            boost_next_epochs = decision.epochs_for_next_window
            prev_k, prev_mae = actual_k, mae

        retry_note = f"  [retried {retry_count}x, {retry_total_epochs} epochs total]" if retry_count else ""
        if verbose:
            print(
                f"  [{window_idx:>2}] [{t_start:.1f}->{t_end:.1f}s] k={actual_k}  "
                f"MAE={mae:.2f}C  true={true_label}{retry_note}  {decision_reason}  "
                f"-> k_next={next_k}  ({train_info['runtime_s']:.0f}s)", flush=True,
            )

        window_results.append({
            "window": window_idx, "t_start": float(t_start), "t_end": float(t_end),
            "k_used": actual_k, "k_next": int(next_k), "mae_C": mae,
            "l2_rel": float(eval_info["l2_rel"]), "true_label": true_label,
            "tm_pred": tm_pred, "decision_reason": decision_reason,
            "runtime_s": float(train_info["runtime_s"]),
            "risk_flag": risk_flag, "diagnosis": diagnosis,
            "n_epochs_used": int(retry_total_epochs), "retry_count": retry_count,
        })

        if boost_next_epochs is not None:
            train_kwargs = dict(train_kwargs, n_epochs=boost_next_epochs)
        elif controller == "tm_hybrid" and train_kwargs["n_epochs"] != base_n_epochs:
            train_kwargs = dict(train_kwargs, n_epochs=base_n_epochs)

        k = next_k
        t_now = t_end

    mean_mae = float(np.mean([w["mae_C"] for w in window_results]))
    max_mae = float(np.max([w["mae_C"] for w in window_results]))
    n_windows = len(window_results)
    n_fem_k1 = int(np.ceil(T_TOTAL / DT_FEM))
    fem_savings_pct = (1.0 - n_windows / n_fem_k1) * 100.0
    total_s = time.time() - t0_total

    # Persist the FINAL trained weights so a later script can load this
    # exact model and query it at arbitrary (x,y,t) without retraining or
    # FEM - see fem_verification_cost_adaptive_control's matching addition
    # and project memory for the "train once, query forever" rationale.
    MODEL_CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    ckpt_path = MODEL_CHECKPOINTS_DIR / f"{geometry}_{arch}_{controller}_seed{model_seed}.pt"
    torch.save({
        "state_dict": model.state_dict(), "arch": arch, "geometry": geometry,
        "controller": controller, "model_seed": model_seed, "dim": DIM,
        "final_t_end": float(t_now),
    }, ckpt_path)

    return {
        "controller": controller, "n_windows": n_windows, "mean_mae": mean_mae,
        "max_mae": max_mae, "fem_savings_pct": fem_savings_pct, "total_s": total_s,
        "checkpoint_path": str(ckpt_path),
        "windows": window_results,
    }


def write_report(alg3: dict, tm: dict, out_path: Path, arch: str, hybrid: dict | None = None) -> None:
    lines = [f"# Algorithm 3 vs TM-guided vs TM-hybrid controller — Rectangle, {arch}, live FEniCS\n"]
    header = "| Metric | Algorithm 3 (threshold) | TM-guided |"
    sep = "|---|---|---|"
    if hybrid is not None:
        header += " TM-hybrid |"
        sep += "---|"
    lines.append(header)
    lines.append(sep)

    def row(label, key, fmt="{:.2f}"):
        cells = [fmt.format(alg3[key]) if isinstance(alg3[key], float) else str(alg3[key]),
                 fmt.format(tm[key]) if isinstance(tm[key], float) else str(tm[key])]
        if hybrid is not None:
            cells.append(fmt.format(hybrid[key]) if isinstance(hybrid[key], float) else str(hybrid[key]))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    row("Windows (FEM calls)", "n_windows", "{}")
    row("FEM savings", "fem_savings_pct", "{:.1f}%")
    row("Mean MAE", "mean_mae", "{:.2f}°C")
    row("Max MAE", "max_mae", "{:.2f}°C")
    row("Total runtime", "total_s", "{:.0f}s")

    lines.append("\n## Algorithm 3 — window-by-window k trajectory\n")
    lines.append("| win | t | k | MAE | true | reason |")
    lines.append("|---|---|---|---|---|---|")
    for w in alg3["windows"]:
        lines.append(
            f"| {w['window']} | {w['t_start']:.1f}-{w['t_end']:.1f} | {w['k_used']} | "
            f"{w['mae_C']:.2f} | {w['true_label']} | {w['decision_reason']} |"
        )

    lines.append("\n## TM-guided — window-by-window k trajectory\n")
    lines.append("| win | t | k | MAE | true | TM pred | reason |")
    lines.append("|---|---|---|---|---|---|---|")
    for w in tm["windows"]:
        lines.append(
            f"| {w['window']} | {w['t_start']:.1f}-{w['t_end']:.1f} | {w['k_used']} | "
            f"{w['mae_C']:.2f} | {w['true_label']} | {w['tm_pred']} | {w['decision_reason']} |"
        )

    if hybrid is not None:
        lines.append("\n## TM-hybrid — window-by-window k trajectory\n")
        lines.append("| win | t | k | MAE | true | epochs (retries) | risk | diagnosis | reason |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for w in hybrid["windows"]:
            epochs_cell = f"{w['n_epochs_used']} ({w.get('retry_count', 0)}x)" if w.get("retry_count") else str(w["n_epochs_used"])
            lines.append(
                f"| {w['window']} | {w['t_start']:.1f}-{w['t_end']:.1f} | {w['k_used']} | "
                f"{w['mae_C']:.2f} | {w['true_label']} | {epochs_cell} | "
                f"{'⚠' if w['risk_flag'] else ''} | {w['diagnosis'] or ''} | {w['decision_reason']} |"
            )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written -> {out_path}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compare Algorithm 3 vs TM-guided adaptive-k, live FEniCS.")
    p.add_argument("--geometry", default="rectangle", choices=["rectangle", "circle", "lshape"])
    p.add_argument("--arch", default="bayesian", choices=["bayesian", "nsga2", "nsga3"])
    p.add_argument("--resolution", type=int, default=30)
    p.add_argument("--model-seed", type=int, default=42)
    p.add_argument("--n-eval", type=int, default=500)
    p.add_argument("--bits-per-feature", type=int, default=8)
    p.add_argument("--clauses", type=int, default=60)
    p.add_argument("--T", type=int, default=10)
    p.add_argument("--s", type=float, default=3.0)
    p.add_argument("--tm-epochs", type=int, default=50)
    p.add_argument("--n-epochs", type=int, default=None)
    p.add_argument("--lbfgs-iters", type=int, default=None)
    p.add_argument("--k-max", type=int, default=None,
                    help="Override K_MAX_=5 for all three controllers (e.g. 10, to see "
                         "where tm_hybrid naturally caps out - see plan memory).")
    p.add_argument("--no-hybrid", action="store_true",
                    help="Skip the tm_hybrid controller, only run algorithm3+tm_guided "
                         "(old two-controller behavior).")
    p.add_argument("--cuda", action="store_true")
    p.add_argument("--device", default=None)
    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.device is not None:
        device = torch.device(args.device)
    elif args.cuda:
        device = torch.device("cuda")
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}  geometry: {args.geometry}", flush=True)

    tm_model, tm_encoder = fit_tm_on_all_data(
        args.bits_per_feature, args.clauses, args.T, args.s, args.tm_epochs,
        geometry=args.geometry,
    )

    train_kwargs = dict(TRAIN_KWARGS)
    if args.n_epochs is not None:
        train_kwargs["n_epochs"] = args.n_epochs
    if args.lbfgs_iters is not None:
        train_kwargs["lbfgs_iters"] = args.lbfgs_iters

    alg3 = run_window_loop(
        controller="algorithm3", arch=args.arch, device=device, resolution=args.resolution,
        model_seed=args.model_seed, train_kwargs=train_kwargs, n_eval=args.n_eval,
        k_max=args.k_max, geometry=args.geometry,
    )
    tm = run_window_loop(
        controller="tm_guided", arch=args.arch, device=device, resolution=args.resolution,
        model_seed=args.model_seed, train_kwargs=train_kwargs, n_eval=args.n_eval,
        tm_model=tm_model, tm_encoder=tm_encoder, k_max=args.k_max, geometry=args.geometry,
    )
    hybrid = None
    if not args.no_hybrid:
        hybrid = run_window_loop(
            controller="tm_hybrid", arch=args.arch, device=device, resolution=args.resolution,
            model_seed=args.model_seed, train_kwargs=train_kwargs, n_eval=args.n_eval,
            tm_model=tm_model, tm_encoder=tm_encoder, k_max=args.k_max, geometry=args.geometry,
        )

    # rectangle keeps the original flat reports/ layout (backward compat);
    # circle/lshape get their own reports/{geometry}/ subfolder - see
    # "Ortak kod + geometriye göre ayrı sonuç klasörleri" memory decision.
    out_dir = RESULTS_DIR / args.geometry
    out_dir.mkdir(parents=True, exist_ok=True)
    out_tag = f"_{args.arch}" if args.arch != "bayesian" else ""
    if args.model_seed != 42:
        out_tag += f"_seed{args.model_seed}"
    dump = {"algorithm3": alg3, "tm_guided": tm}
    if hybrid is not None:
        dump["tm_hybrid"] = hybrid
    with open(out_dir / f"compare_controllers{out_tag}.json", "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=2)
    write_report(alg3, tm, out_dir / f"compare_report{out_tag}.md", args.arch, hybrid=hybrid)

    print("\n=== SUMMARY ===")
    print(f"Algorithm 3 : windows={alg3['n_windows']}  savings={alg3['fem_savings_pct']:.1f}%  "
          f"mean_mae={alg3['mean_mae']:.2f}C  max_mae={alg3['max_mae']:.2f}C")
    print(f"TM-guided   : windows={tm['n_windows']}  savings={tm['fem_savings_pct']:.1f}%  "
          f"mean_mae={tm['mean_mae']:.2f}C  max_mae={tm['max_mae']:.2f}C")
    if hybrid is not None:
        print(f"TM-hybrid   : windows={hybrid['n_windows']}  savings={hybrid['fem_savings_pct']:.1f}%  "
              f"mean_mae={hybrid['mean_mae']:.2f}C  max_mae={hybrid['max_mae']:.2f}C")


if __name__ == "__main__":
    main()
