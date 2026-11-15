"""Verification for any future flood or landslide model (audit P2): skill scores, honest splits and a leakage guard.

Nothing here makes a forecast. It is the yardstick a model must pass before the readiness engine lets it be called more
than "model required": out-of-sample POD, FAR and CSI on a chronological test period, with inputs restricted to what
existed at each issue time.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np


@dataclass(frozen=True)
class Contingency:
    hits: int
    misses: int
    false_alarms: int
    correct_negatives: int = 0

    @property
    def pod(self) -> float | None:
        """Probability of detection: hits / observed events."""
        n = self.hits + self.misses
        return self.hits / n if n else None

    @property
    def far(self) -> float | None:
        """False alarm ratio: false alarms / warnings issued."""
        n = self.hits + self.false_alarms
        return self.false_alarms / n if n else None

    @property
    def csi(self) -> float | None:
        """Critical success index: hits / (hits + misses + false alarms)."""
        n = self.hits + self.misses + self.false_alarms
        return self.hits / n if n else None

    @property
    def bias(self) -> float | None:
        """Frequency bias: warnings issued / events observed. 1 means as many warnings as events."""
        n = self.hits + self.misses
        return (self.hits + self.false_alarms) / n if n else None

    def as_dict(self) -> dict:
        r = lambda v: None if v is None else round(v, 3)  # noqa: E731
        return {"hits": self.hits, "misses": self.misses, "falseAlarms": self.false_alarms, "correctNegatives": self.correct_negatives,
                "pod": r(self.pod), "far": r(self.far), "csi": r(self.csi), "bias": r(self.bias)}


def contingency(predicted: np.ndarray, observed: np.ndarray) -> Contingency:
    """Day-by-day (or cell-by-cell) yes/no comparison of equal-length boolean series."""
    p, o = np.asarray(predicted, bool), np.asarray(observed, bool)
    if p.shape != o.shape:
        raise ValueError("predicted and observed differ in shape")
    return Contingency(int((p & o).sum()), int((~p & o).sum()), int((p & ~o).sum()), int((~p & ~o).sum()))


def match_events(warnings: list[date], events: list[date], window_days: int = 1) -> Contingency:
    """Event-based scoring: an event is hit when a warning falls within window_days before it (or on the day); a warning
    with no event in the window after it is a false alarm. Each warning can match one event, closest first."""
    ws, es = sorted(warnings), sorted(events)
    used = [False] * len(ws)
    hits = 0
    for e in es:
        best = None
        for i, w in enumerate(ws):
            lead = (e - w).days
            if not used[i] and 0 <= lead <= window_days and (best is None or lead < (e - ws[best]).days):
                best = i
        if best is not None:
            used[best] = True
            hits += 1
    return Contingency(hits, len(es) - hits, used.count(False))


def chronological_split(times: list, train_end, validate_end) -> tuple[list[int], list[int], list[int]]:
    """Indices for train (up to train_end), validate (to validate_end) and test (after). Never shuffled: a model is always
    tested on a period after everything it learned from."""
    tr = [i for i, t in enumerate(times) if t <= train_end]
    va = [i for i, t in enumerate(times) if train_end < t <= validate_end]
    te = [i for i, t in enumerate(times) if t > validate_end]
    return tr, va, te


def available_by(records: list[dict], issue_time: datetime) -> list[dict]:
    """The leakage guard: only records the provider had published at the issue time. A record without available_at is
    refused rather than assumed early."""
    out = []
    for r in records:
        av = r.get("available_at")
        if av is None:
            continue
        t = datetime.fromisoformat(str(av).replace("Z", "+00:00"))
        it = issue_time if issue_time.tzinfo else issue_time.replace(tzinfo=t.tzinfo)
        if t <= it:
            out.append(r)
    return out


def spatial_blocks(x: np.ndarray, y: np.ndarray, block_m: float, folds: int, seed: int = 0) -> np.ndarray:
    """Fold number per sample from square spatial blocks, so neighbouring pixels never sit on both sides of a split.
    x, y in projected metres. Blocks are shuffled into folds with a fixed seed, so the split is reproducible."""
    bx, by = np.floor(np.asarray(x) / block_m).astype(np.int64), np.floor(np.asarray(y) / block_m).astype(np.int64)
    keys = sorted(set(zip(bx.tolist(), by.tolist())))
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(keys))
    fold_of = {k: int(order[i] % folds) for i, k in enumerate(keys)}
    return np.array([fold_of[k] for k in zip(bx.tolist(), by.tolist())])


def auc(score: np.ndarray, positive: np.ndarray) -> float | None:
    """Area under the ROC curve by the rank method (ties shared). None without both classes."""
    s, p = np.asarray(score, float), np.asarray(positive, bool)
    n1, n0 = int(p.sum()), int((~p).sum())
    if not n1 or not n0:
        return None
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s))
    sorted_s = s[order]
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and sorted_s[j + 1] == sorted_s[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return float((ranks[p].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def days(start: date, end: date) -> list[date]:
    return [start + timedelta(d) for d in range((end - start).days + 1)]


def nse(sim: np.ndarray, obs: np.ndarray) -> float:
    """Nash-Sutcliffe efficiency for discharge: 1 is perfect, 0 is no better than the observed mean."""
    s, o = np.asarray(sim, float), np.asarray(obs, float)
    ok = np.isfinite(s) & np.isfinite(o)
    den = float(((o[ok] - o[ok].mean()) ** 2).sum())
    return math.nan if den == 0 else 1 - float(((s[ok] - o[ok]) ** 2).sum()) / den


def windowed(warn: np.ndarray, obs: np.ndarray, lead_min: int, lead_max: int) -> Contingency:
    """Scoring on a grid of days (axis 0) by places (other axes). An observed event on day t is hit when the same place
    had a warning issued on a day from t - lead_max to t - lead_min; a warning on day t is a false alarm when no event
    follows at that place from t + lead_min to t + lead_max. Hits and misses count events, false alarms count warnings
    (as match_events does). Events too early to have a warning in range, and warnings whose range runs past the end, are
    left out, so the edges never count against or for a forecast."""
    w, o = np.asarray(warn, bool), np.asarray(obs, bool)
    if w.shape != o.shape:
        raise ValueError("warn and obs differ in shape")
    n = w.shape[0]
    covered = np.zeros_like(o)  # an event day with a warning in range before it
    followed = np.zeros_like(w)  # a warning day with an event in range after it
    for k in range(lead_min, lead_max + 1):
        if k < n:
            covered[k:] |= w[: n - k]
            followed[: n - k] |= o[k:]
    ev = o[lead_max:]
    hits = int((ev & covered[lead_max:]).sum())
    misses = int((ev & ~covered[lead_max:]).sum())
    fa = int((w[: n - lead_max] & ~followed[: n - lead_max]).sum())
    quiet = int((~w[: n - lead_max] & ~followed[: n - lead_max]).sum())
    return Contingency(hits, misses, fa, quiet)


def shuffled_csi(warn: np.ndarray, obs: np.ndarray, blocks: np.ndarray, lead_min: int, lead_max: int, n: int = 1000,
                 seed: int = 0) -> np.ndarray:
    """CSI of random warnings that keep each place's number of warnings in each block of days (such as each calendar month):
    the chance level a real warning must beat. blocks gives a block label per day (axis 0)."""
    w = np.asarray(warn, bool).reshape(warn.shape[0], -1)
    rng = np.random.default_rng(seed)
    idx = [np.flatnonzero(blocks == b) for b in np.unique(blocks)]
    out = np.empty(n)
    for i in range(n):
        s = np.empty_like(w)
        for rows in idx:
            sub = w[rows]
            s[rows] = sub[rng.permuted(np.tile(np.arange(len(rows))[:, None], (1, sub.shape[1])), axis=0), np.arange(sub.shape[1])]
        c = windowed(s.reshape(warn.shape), obs, lead_min, lead_max).csi
        out[i] = np.nan if c is None else c
    return out
