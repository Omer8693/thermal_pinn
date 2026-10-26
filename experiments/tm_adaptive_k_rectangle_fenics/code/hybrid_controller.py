"""
experiments/tm_adaptive_k_rectangle_fenics/hybrid_controller.py
=====================================================================
Shared decision logic for the "tm_hybrid" controller, imported by both
compare_controllers.py and field_snapshots.py (which already duplicate
the core while-loop for each other - this keeps the *decision* logic
single-sourced instead of copy-pasted twice).

tm_hybrid extends tm_guided (same TM SAFE/UNSAFE call drives k+-1, see
fit_tm_on_all_data / tm_predict_row in compare_controllers.py - no new
classifier here) with two complementary safety mechanisms:

1. retry_until_safe() - REACTIVE, fixes the CURRENT window: if a window
   comes back truly UNSAFE (mae_C > accept threshold), keep training it
   IN PLACE (train_window does not reset the model, so calling it again
   just continues optimizing from the current weights) in
   RETRY_INCREMENT-epoch slices, re-evaluating after each slice, until
   it's SAFE or MAX_TOTAL_EPOCHS is hit (6400 total epochs, matching
   the already-validated 800->6400 fix for the
   NSGA-II/III cold-start freeze - see
   tm_adaptive_k_rectangle_experiment.md memory). This is what actually
   moves Max MAE, not just Mean MAE - the first version of tm_hybrid
   (boost-next-window only) could never fix the window that triggered
   the flag, only prevent the failure from cascading into later windows.
2. decide() - PROACTIVE, protects the NEXT window: whenever k grows AND
   MAE also grows (a leading indicator, even if this window still ended
   up SAFE after retrying) or TM predicts UNSAFE, diagnose() explains
   the likely cause from the window's own diagnostics, and the NEXT
   window's epoch budget is boosted (BOOST_FACTOR x), capped at
   MAX_BOOST_STREAK consecutive windows so a pathological run can't keep
   boosting forever - this is the "finish safely" bound for mechanism 2.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_features import load_raw_runs, to_dataframe

BOOST_FACTOR = 8
MAX_BOOST_STREAK = 3

RETRY_INCREMENT = 800
MAX_TOTAL_EPOCHS = 6400  # proven-safe ceiling (800->6400 fixed all NSGA-II/III freezes,
# see memory) - a TOTAL cap, not a retry count, so a window whose base_epochs was
# already boosted by decide() (mechanism 2) to 6400 can't stack retries on top of that
# and run away past the proven-safe budget; it simply gets 0 retries in that case.


@dataclass
class HybridState:
    """Carried across windows by the caller's loop."""
    boost_streak: int = 0


@dataclass
class HybridDecision:
    next_k: int
    reason: str
    risk_flag: bool
    diagnosis: str | None
    epochs_for_next_window: int | None  # None = no override, caller uses its default


_LOSS_END_SAFE_P90_CACHE: dict[str, float] = {}  # lazily computed per geometry, module-level cache
_RAW_RUNS_DIR = Path(__file__).resolve().parent.parent / "raw_runs"


def _loss_end_safe_band(geometry: str = "rectangle") -> float:
    """90th percentile of loss_end among SAFE-labelled rows in the fixed-k
    sweep data (raw_runs/{geometry}/*_k{1..5}_*_live_features.json) - the
    same signal TM's own strongest learned rule already keys on (see
    memory: "IF NOT loss_end>=0.000532 THEN SAFE"). Computed once per
    geometry, lazily, pooling every arch currently on disk for that
    geometry - the freeze signature is architecture-independent (see
    memory: byte-identical grad_mean=pde_residual_mean=0 between bayesian
    and nsga2)."""
    if geometry not in _LOSS_END_SAFE_P90_CACHE:
        df = to_dataframe(load_raw_runs(raw_dir=_RAW_RUNS_DIR / geometry))
        safe_loss_end = df.loc[df["label"] == "SAFE", "loss_end"]
        _LOSS_END_SAFE_P90_CACHE[geometry] = float(np.percentile(safe_loss_end, 90))
    return _LOSS_END_SAFE_P90_CACHE[geometry]


def diagnose(row: dict, geometry: str = "rectangle") -> str | None:
    """Looks at this window's own diagnostics and returns a short, human-
    readable likely cause, or None if nothing stands out. Checks loss_end
    (FEM end-supervision) first - it is the feature that actually caught
    the cold-start freeze that residual/gradient missed entirely (they
    read exactly 0.0 when frozen, see memory) - then falls back to
    grad_mean/pde_residual_mean collapsing to ~0, the frozen-state
    fingerprint itself."""
    band = _loss_end_safe_band(geometry)
    loss_end = row.get("loss_end")
    grad_mean = row.get("grad_mean")
    pde_res = row.get("pde_residual_mean")

    if loss_end is not None and loss_end > band:
        return (f"loss_end={loss_end:.2e} exceeds SAFE band (p90={band:.2e} over "
                f"fixed-k sweep) - window end likely undertrained")
    if grad_mean is not None and pde_res is not None and grad_mean < 1e-6 and pde_res < 1e-6:
        return "grad_mean/pde_residual_mean ~= 0 - network frozen at IC (clamp saturation)"
    return None


def decide(*, prev_k: int, prev_mae: float, mae: float, actual_k: int,
           tm_pred: str, row: dict, state: HybridState,
           k_min: int, k_max: int, base_epochs: int, geometry: str = "rectangle") -> HybridDecision:
    """prev_k/prev_mae: the PREVIOUS window's k_used/mae_C. For window 1
    (no previous window), the caller should pass prev_k=actual_k and
    prev_mae=mae for that first call - this makes the "k grew but MAE
    grew too" check trivially False (there's nothing to compare against
    yet), leaving tm_pred=="UNSAFE" as the only possible risk source."""
    if tm_pred == "UNSAFE":
        next_k = max(k_min, actual_k - 1)
    else:
        next_k = min(k_max, actual_k + 1)

    grew_but_worse = actual_k > prev_k and mae > prev_mae
    risk_flag = grew_but_worse or tm_pred == "UNSAFE"

    diagnosis = diagnose(row, geometry) if risk_flag else None

    if risk_flag and state.boost_streak < MAX_BOOST_STREAK:
        state.boost_streak += 1
        epochs_for_next_window = base_epochs * BOOST_FACTOR
    else:
        if not risk_flag:
            state.boost_streak = 0
        epochs_for_next_window = None

    reason_bits = [f"TM predicted {tm_pred}"]
    if grew_but_worse:
        reason_bits.append(f"k grew {prev_k}->{actual_k} but MAE grew {prev_mae:.2f}->{mae:.2f}C")
    if diagnosis:
        reason_bits.append(f"diagnosis: {diagnosis}")
    if epochs_for_next_window:
        reason_bits.append(f"-> boosting next window to {epochs_for_next_window} epochs "
                            f"(streak {state.boost_streak}/{MAX_BOOST_STREAK})")
    reason = "; ".join(reason_bits)

    return HybridDecision(
        next_k=next_k, reason=reason, risk_flag=risk_flag,
        diagnosis=diagnosis, epochs_for_next_window=epochs_for_next_window,
    )


@dataclass
class RetryResult:
    train_info: dict
    eval_info: dict
    retry_count: int
    total_epochs: int


def retry_until_safe(*, train_epochs_fn, eval_fn, base_epochs: int, accept_thresh_C: float,
                      increment: int = RETRY_INCREMENT,
                      max_total_epochs: int = MAX_TOTAL_EPOCHS) -> RetryResult:
    """Generic retry-in-place loop, decoupled from any specific training
    setup so it can be reused by the online adaptive-k loop
    (compare_controllers.py), a fixed-k sweep (feature_logging_run.py),
    or the single-leap experiment - all three just need to hand it two
    closures:
        train_epochs_fn(n_epochs) -> train_info   (trains the model IN
            PLACE for n_epochs more steps and returns train_window()'s
            result dict - caller's closure owns model/domain/window)
        eval_fn() -> eval_info                     (re-evaluates the
            current model state - caller's closure owns model/domain/window)

    Trains for base_epochs first; if the result is still UNSAFE (mae_C >
    accept_thresh_C), keeps calling train_epochs_fn(increment) and
    re-evaluating until SAFE, or total_epochs would exceed max_total_epochs
    - whichever comes first. The cap is on TOTAL epochs spent on this
    window, not a retry count: if base_epochs is already close to (or at)
    max_total_epochs - e.g. this window's budget was already boosted by
    decide()'s proactive mechanism - it simply gets fewer (or zero)
    retries, so a window can never run away past the proven-safe 6400
    budget regardless of where it started. This is the "finish safely"
    bound: a window that never recovers is still returned (with its
    best-effort result), the caller always gets to move on rather than
    looping forever."""
    train_info = train_epochs_fn(base_epochs)
    eval_info = eval_fn()
    retry_count = 0
    total_epochs = base_epochs
    while eval_info["mae_C"] > accept_thresh_C and total_epochs + increment <= max_total_epochs:
        retry_count += 1
        train_info = train_epochs_fn(increment)
        eval_info = eval_fn()
        total_epochs += increment
    return RetryResult(train_info=train_info, eval_info=eval_info,
                        retry_count=retry_count, total_epochs=total_epochs)


@dataclass
class BestResult:
    train_info: dict
    eval_info: dict
    best_epochs: int    # epoch count at which the best result was reached
    epochs_tried: int   # total epochs actually trained (>= best_epochs, includes the plateau tail)


PLATEAU_PATIENCE = 3  # stop after this many increments in a row with no improvement


def train_to_best(*, train_epochs_fn, eval_fn, get_state_fn, set_state_fn, base_epochs: int,
                   increment: int = RETRY_INCREMENT, max_total_epochs: int = MAX_TOTAL_EPOCHS,
                   patience: int = PLATEAU_PATIENCE) -> BestResult:
    """Answers "how good can this window get", not "how little training is
    enough" (that's what retry_until_safe does - it stops at the FIRST
    safe result, which can be a lucky, barely-passing number - see the
    single-leap experiment's 9.94C leap result, uncomfortably close to
    the 10C threshold, that motivated this function).

    Keeps training in `increment`-epoch slices, tracking the best (lowest
    mae_C) result seen so far. Since train_window mutates the model
    in-place and later training can make things WORSE (not just plateau),
    the model's weights are checkpointed at every new best via
    get_state_fn()/set_state_fn() - both caller-owned closures, e.g.
    get_state_fn=lambda: {k: v.clone() for k, v in model.state_dict().items()},
    set_state_fn=model.load_state_dict - and RESTORED to that best
    checkpoint before returning, so the model a caller ends up with always
    matches the reported best eval_info, even if training continued past
    it. Stops when there has been no improvement for `patience`
    consecutive slices (a plateau - further training is very unlikely to
    help) or max_total_epochs is reached, whichever comes first."""
    train_info = train_epochs_fn(base_epochs)
    eval_info = eval_fn()
    total_epochs = base_epochs
    best_mae = eval_info["mae_C"]
    best_state = get_state_fn()
    best_train_info, best_eval_info, best_epochs = train_info, eval_info, total_epochs
    no_improve_streak = 0

    while total_epochs + increment <= max_total_epochs and no_improve_streak < patience:
        train_info = train_epochs_fn(increment)
        eval_info = eval_fn()
        total_epochs += increment
        if eval_info["mae_C"] < best_mae - 1e-6:
            best_mae = eval_info["mae_C"]
            best_state = get_state_fn()
            best_train_info, best_eval_info, best_epochs = train_info, eval_info, total_epochs
            no_improve_streak = 0
        else:
            no_improve_streak += 1

    set_state_fn(best_state)
    return BestResult(train_info=best_train_info, eval_info=best_eval_info,
                       best_epochs=best_epochs, epochs_tried=total_epochs)
