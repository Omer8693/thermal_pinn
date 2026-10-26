"""
experiments/tm_adaptive_k_rectangle_fenics/binarize.py
=========================================================
Thermometer encoding for the Tsetlin Machine, same scheme as the
non-FEniCS experiment (see that folder's binarize.py for the full
rationale): quantile-based "value >= threshold" bits fit on the TRAIN
split only, plus one-hot for phase/arch and a thermometer for k.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_features import CATEGORICAL_FEATURES, CONTINUOUS_FEATURES, K_MAX


class ThermometerEncoder:
    def __init__(self, n_bits: int = 8):
        self.n_bits = n_bits
        self.thresholds: dict[str, list[float]] = {}
        self.categories = CATEGORICAL_FEATURES
        self.bit_names: list[str] = []

    def fit(self, df: pd.DataFrame) -> "ThermometerEncoder":
        self.thresholds = {}
        for feat in CONTINUOUS_FEATURES:
            qs = np.linspace(0, 1, self.n_bits + 2)[1:-1]
            self.thresholds[feat] = sorted(set(np.quantile(df[feat].values, qs).tolist()))
        self._build_bit_names()
        return self

    def _build_bit_names(self) -> None:
        names = []
        for feat in CONTINUOUS_FEATURES:
            for t in self.thresholds[feat]:
                names.append(f"{feat}>={t:.4g}")
        for feat, cats in self.categories.items():
            for c in cats:
                names.append(f"{feat}=={c}")
        for i in range(1, K_MAX + 1):
            names.append(f"k>={i}")
        self.bit_names = names

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        n = len(df)
        cols = []
        for feat in CONTINUOUS_FEATURES:
            thr = np.array(self.thresholds[feat])
            vals = df[feat].values.reshape(-1, 1)
            cols.append((vals >= thr.reshape(1, -1)).astype(np.uint32))
        for feat, cats in self.categories.items():
            onehot = np.zeros((n, len(cats)), dtype=np.uint32)
            for j, c in enumerate(cats):
                onehot[:, j] = (df[feat].values == c).astype(np.uint32)
            cols.append(onehot)
        k_vals = df["k"].values.reshape(-1, 1)
        thermo_k = (k_vals >= np.arange(1, K_MAX + 1).reshape(1, -1)).astype(np.uint32)
        cols.append(thermo_k)
        return np.concatenate(cols, axis=1)

    def fit_transform(self, df: pd.DataFrame) -> np.ndarray:
        self.fit(df)
        return self.transform(df)

    def save(self, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"n_bits": self.n_bits, "thresholds": self.thresholds,
                       "bit_names": self.bit_names}, f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "ThermometerEncoder":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        enc = cls(n_bits=data["n_bits"])
        enc.thresholds = data["thresholds"]
        enc.bit_names = data["bit_names"]
        return enc


def encode_label(labels: pd.Series) -> np.ndarray:
    """UNSAFE -> 1 (do not promote / demote), SAFE -> 0 (promotion OK)."""
    return (labels.values == "UNSAFE").astype(np.uint32)
