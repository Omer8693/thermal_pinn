"""
experiments/tm_adaptive_k_rectangle_fenics/train_tm.py
=========================================================
Trains a Tsetlin Machine as a binary SAFE/UNSAFE promotion-safety verifier
on the live-FEniCS fixed-k sweep data (Rectangle, bayesian).

Split: leave-one-k-out (default: hold out k=5 entirely) rather than a
random window split - with only 46 rows and 5 k-groups, this is the only
split that tests genuine generalisation (to an unseen window width)
instead of memorising the 46 rows.

Usage
-----
    cd thermal_pinn/experiments/tm_adaptive_k_rectangle_fenics
    python3 extract_features.py
    python3 train_tm.py --held-out-k 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from binarize import ThermometerEncoder, encode_label
from extract_features import load_raw_runs, to_dataframe

from tmu.models.classification.vanilla_classifier import TMClassifier

RESULTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def describe_clause(model: TMClassifier, clause: int, the_class: int, polarity: int,
                     bit_names: list[str]) -> str | None:
    n_feat = len(bit_names)
    literals = []
    for ta in range(2 * n_feat):
        if model.get_ta_action(clause, ta, the_class=the_class, polarity=polarity):
            if ta < n_feat:
                literals.append(bit_names[ta])
            else:
                literals.append(f"NOT {bit_names[ta - n_feat]}")
    if not literals:
        return None
    weight = model.get_weight(the_class, polarity, clause)
    sign = "+" if polarity == 0 else "-"
    label = "UNSAFE" if the_class == 1 else "SAFE"
    return f"[w={sign}{weight:.1f}] IF {' AND '.join(literals)} THEN {label}"


def dump_rules(model: TMClassifier, bit_names: list[str], n_clauses: int, out_path: Path,
               max_per_class: int = 8) -> None:
    lines = []
    for the_class, label in [(1, "UNSAFE"), (0, "SAFE")]:
        lines.append(f"\n## {label}")
        for polarity, pol_name in [(0, "positive (votes FOR)"), (1, "negative (votes AGAINST)")]:
            lines.append(f"\n### {pol_name}")
            shown = 0
            for clause in range(n_clauses):
                text = describe_clause(model, clause, the_class, polarity, bit_names)
                if text is None:
                    continue
                lines.append(f"- {text}")
                shown += 1
                if shown >= max_per_class:
                    break
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Rules written -> {out_path}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Train TM SAFE/UNSAFE verifier on Rectangle live-FEM sweep.")
    p.add_argument("--held-out-k", type=int, default=5, help="k value used entirely as test set")
    p.add_argument("--bits-per-feature", type=int, default=8)
    p.add_argument("--clauses", type=int, default=60)
    p.add_argument("--T", type=int, default=10)
    p.add_argument("--s", type=float, default=3.0)
    p.add_argument("--epochs", type=int, default=50)
    return p


def main() -> None:
    args = build_parser().parse_args()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    runs = load_raw_runs()
    df = to_dataframe(runs)
    print(f"Loaded {len(df)} windows. label counts:\n{df['label'].value_counts()}")
    print(f"per-k label counts:\n{df.groupby('k')['label'].value_counts()}")

    train_mask = df["k"] != args.held_out_k
    test_mask = df["k"] == args.held_out_k
    df_train, df_test = df[train_mask].reset_index(drop=True), df[test_mask].reset_index(drop=True)
    print(f"train={len(df_train)} (k != {args.held_out_k})  test={len(df_test)} (k == {args.held_out_k})")

    encoder = ThermometerEncoder(n_bits=args.bits_per_feature).fit(df_train)
    X_train = encoder.transform(df_train)
    X_test = encoder.transform(df_test)
    Y_train = encode_label(df_train["label"])
    Y_test = encode_label(df_test["label"])
    encoder.save(RESULTS_DIR / "encoder.json")

    model = TMClassifier(
        number_of_clauses=args.clauses, T=args.T, s=args.s,
        platform="CPU", weighted_clauses=True,
    )

    train_acc = test_acc = float("nan")
    for epoch in range(args.epochs):
        model.fit(X_train, Y_train)
        train_acc = float(np.mean(model.predict(X_train) == Y_train))
        test_acc = float(np.mean(model.predict(X_test) == Y_test))
        print(f"epoch {epoch + 1:>3}/{args.epochs}  train_acc={train_acc:.3f}  test_acc={test_acc:.3f}")

    test_pred = model.predict(X_test)
    print("Test predictions vs truth (k held out):")
    for i in range(len(df_test)):
        row = df_test.iloc[i]
        pred_label = "UNSAFE" if test_pred[i] == 1 else "SAFE"
        mark = "OK" if pred_label == row["label"] else "WRONG"
        print(f"  win{row['window']} t=[{row['t_start']:.1f},{row['t_end']:.1f}] "
              f"mae={row['mae_C']:.2f} true={row['label']} pred={pred_label}  {mark}")

    dump_rules(model, encoder.bit_names, args.clauses, RESULTS_DIR / "tm_rules.md")

    report = {
        "n_train": len(df_train), "n_test": len(df_test), "held_out_k": args.held_out_k,
        "final_train_acc": train_acc, "final_test_acc": test_acc,
        "hyperparams": vars(args),
    }
    with open(RESULTS_DIR / "tm_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
