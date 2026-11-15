"""Landslide susceptibility (L1) by logistic regression: transparent coefficients, suited to a small inventory. Validated
only with spatial block cross-validation (cascade_lens.verify.spatial_blocks), never with randomly shuffled pixels, and
unmapped ground is treated as unlabelled background, not as a confirmed absence."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .. import verify


@dataclass
class Logistic:
    names: list[str]
    mean: np.ndarray
    scale: np.ndarray
    coef: np.ndarray  # intercept first, then one per standardised feature

    def probability(self, X: np.ndarray) -> np.ndarray:
        z = (np.asarray(X, float) - self.mean) / self.scale
        return 1 / (1 + np.exp(-(self.coef[0] + z @ self.coef[1:])))

    def table(self) -> list[dict]:
        """Coefficient per standardised feature: the change in log-odds for one standard deviation."""
        return [{"feature": n, "logOddsPerSd": round(float(c), 3)} for n, c in zip(self.names, self.coef[1:])]


def fit(X: np.ndarray, y: np.ndarray, names: list[str], ridge: float = 1e-3, iters: int = 50) -> Logistic:
    """Iteratively reweighted least squares with a small ridge penalty (not on the intercept), on standardised features."""
    X, y = np.asarray(X, float), np.asarray(y, float)
    mean, scale = X.mean(0), X.std(0)
    scale[scale == 0] = 1
    Z = np.column_stack([np.ones(len(X)), (X - mean) / scale])
    w = np.zeros(Z.shape[1])
    pen = np.eye(Z.shape[1]) * ridge
    pen[0, 0] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(Z @ w)))
        W = np.clip(p * (1 - p), 1e-9, None)
        H = Z.T @ (Z * W[:, None]) + pen
        step = np.linalg.solve(H, Z.T @ (y - p) - pen @ w)
        w += step
        if np.abs(step).max() < 1e-8:
            break
    return Logistic(names=list(names), mean=mean, scale=scale, coef=w)


def block_cv(X: np.ndarray, y: np.ndarray, x_m: np.ndarray, y_m: np.ndarray, names: list[str], block_m: float = 5000, folds: int = 5) -> dict:
    """Out-of-fold AUC by spatial blocks: each fold is predicted by a model that never saw its blocks."""
    fold = verify.spatial_blocks(x_m, y_m, block_m, folds)
    pred = np.full(len(y), np.nan)
    per = []
    for k in range(folds):
        te, tr = fold == k, fold != k
        if not te.any() or len(set(np.asarray(y)[tr].tolist())) < 2:
            continue
        m = fit(np.asarray(X)[tr], np.asarray(y)[tr], names)
        pred[te] = m.probability(np.asarray(X)[te])
        per.append(verify.auc(pred[te], np.asarray(y, bool)[te]))
    ok = np.isfinite(pred)
    return {"aucOutOfFold": verify.auc(pred[ok], np.asarray(y, bool)[ok]), "aucPerFold": per, "folds": folds, "blockM": block_m}
