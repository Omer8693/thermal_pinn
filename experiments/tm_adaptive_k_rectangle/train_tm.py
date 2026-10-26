"""
experiments/tm_adaptive_k_rectangle/train_tm.py
=================================================
Trains a Tsetlin Machine to predict k_next (the skip-factor the v1
adaptive-k controller would assign to the *following* window) from
FEM-free, PINN-only features (PDE residual, gradient, ΔT, Fo, Bi, phase,
k_prev, arch) computed at the end of the current window.

This is the "advanced" multi-class variant from the task brief - the
binary SAFE/UNSAFE @ 10C label turned out to be degenerate for the
Rectangle domain (see README.md), so k_next is the primary target here.

Usage
-----
    cd thermal_pinn/experiments/tm_adaptive_k_rectangle
    python3 extract_features.py          # build results/window_features.csv
    python3 train_tm.py                  # train + evaluate + dump rules
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from binarize import ThermometerEncoder, K_PREV_MAX, encode_k_next, decode_k_class
from extract_features import load_raw_runs, to_dataframe

from tmu.models.classification.vanilla_classifier import TMClassifier

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def make_split(df: pd.DataFrame, test_frac: float, rng_seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Seed-based split when >=3 distinct seeds exist for the dominant arch,
    else a random per-window split (with a loud warning - not a real
    generalisation test, just enough to sanity-check the pipeline)."""
    n_seeds = df["seed"].nunique()
    if n_seeds >= 3:
        seeds = sorted(df["seed"].unique())
        rng = np.random.default_rng(rng_seed)
        n_test = max(1, round(len(seeds) * test_frac))
        test_seeds = set(rng.choice(seeds, size=n_test, replace=False).tolist())
        test_mask = df["seed"].isin(test_seeds).values
        print(f"[split] seed-based: test seeds = {sorted(test_seeds)}")
    else:
        warnings.warn(
            f"Only {n_seeds} distinct seed(s) in the data - falling back to a "
            f"RANDOM per-window split. This is a pipeline sanity check only, "
            f"NOT a real generalisation test. Run more seeds "
            f"(feature_logging_run.py --n-seeds ...) before drawing conclusions."
        )
        rng = np.random.default_rng(rng_seed)
        idx = rng.permutation(len(df))
        n_test = max(1, round(len(df) * test_frac))
        test_idx = set(idx[:n_test].tolist())
        test_mask = np.array([i in test_idx for i in range(len(df))])
    return ~test_mask, test_mask


def describe_clause(model: TMClassifier, clause: int, the_class: int, polarity: int,
                     bit_names: list[str]) -> str:
    n_feat = len(bit_names)
    literals = []
    for ta in range(2 * n_feat):
        if model.get_ta_action(clause, ta, the_class=the_class, polarity=polarity):
            if ta < n_feat:
                literals.append(bit_names[ta])
            else:
                literals.append(f"NOT {bit_names[ta - n_feat]}")
    weight = model.get_weight(the_class, polarity, clause)
    sign = "+" if polarity == 0 else "-"
    body = " AND ".join(literals) if literals else "(always true)"
    return f"[w={sign}{weight:.1f}] IF {body} THEN k_next={decode_k_class(the_class)}"


def dump_rules(model: TMClassifier, bit_names: list[str], classes: list[int],
                clauses_per_class: int, out_path: Path, max_per_class: int = 6) -> None:
    lines = []
    for the_class in classes:
        lines.append(f"\n## k_next = {decode_k_class(the_class)}")
        for polarity in (0, 1):
            pol_name = "positive (votes FOR)" if polarity == 0 else "negative (votes AGAINST)"
            lines.append(f"\n### {pol_name} clauses")
            shown = 0
            for clause in range(clauses_per_class):
                n_incl = model.number_of_include_actions(the_class, clause) if hasattr(
                    model, "number_of_include_actions") else None
                text = describe_clause(model, clause, the_class, polarity, bit_names)
                if "(always true)" in text:
                    continue
                lines.append(f"- {text}")
                shown += 1
                if shown >= max_per_class:
                    break
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Rules written -> {out_path}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Train a Tsetlin Machine on Rectangle adaptive-k window features.")
    p.add_argument("--bits-per-feature", type=int, default=8)
    p.add_argument("--clauses", type=int, default=200, help="clauses per class (split half pos / half neg)")
    p.add_argument("--T", type=int, default=15)
    p.add_argument("--s", type=float, default=3.0)
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--test-frac", type=float, default=0.3)
    p.add_argument("--seed", type=int, default=0)
    return p


def main() -> None:
    args = build_parser().parse_args()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    runs = load_raw_runs()
    df = to_dataframe(runs)
    print(f"Loaded {len(df)} windows (k_next labelled) from {len(runs)} run(s).")
    print("k_next distribution:\n", df["k_next"].value_counts().sort_index())

    train_mask, test_mask = make_split(df, args.test_frac, args.seed)
    df_train, df_test = df[train_mask].reset_index(drop=True), df[test_mask].reset_index(drop=True)
    print(f"train={len(df_train)}  test={len(df_test)}")

    encoder = ThermometerEncoder(n_bits=args.bits_per_feature).fit(df_train)
    X_train = encoder.transform(df_train)
    X_test = encoder.transform(df_test) if len(df_test) else np.zeros((0, X_train.shape[1]), dtype=np.uint32)
    Y_train = encode_k_next(df_train["k_next"])
    Y_test = encode_k_next(df_test["k_next"]) if len(df_test) else np.zeros((0,), dtype=np.uint32)

    encoder.save(RESULTS_DIR / "encoder.json")

    model = TMClassifier(
        number_of_clauses=args.clauses, T=args.T, s=args.s,
        platform="CPU", weighted_clauses=True,
    )

    best_acc = -1.0
    for epoch in range(args.epochs):
        model.fit(X_train, Y_train)
        train_acc = float(np.mean(model.predict(X_train) == Y_train))
        if len(X_test):
            test_acc = float(np.mean(model.predict(X_test) == Y_test))
        else:
            test_acc = float("nan")
        best_acc = max(best_acc, test_acc if not np.isnan(test_acc) else train_acc)
        print(f"epoch {epoch + 1:>3}/{args.epochs}  train_acc={train_acc:.3f}  test_acc={test_acc:.3f}")

    classes_present = sorted(set(Y_train.tolist()) | set(Y_test.tolist()))
    clauses_per_class = args.clauses  # tmu splits pos/neg internally per class
    dump_rules(model, encoder.bit_names, classes_present, clauses_per_class,
               RESULTS_DIR / "tm_rules.md")

    report = {
        "n_train": len(df_train), "n_test": len(df_test),
        "final_train_acc": train_acc, "final_test_acc": test_acc,
        "classes_present": classes_present,
        "hyperparams": vars(args),
    }
    with open(RESULTS_DIR / "tm_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
