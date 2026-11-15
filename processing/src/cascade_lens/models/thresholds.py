"""Empirical rainfall thresholds for landslide triggering (L2/L3): cumulated event rainfall E against event duration D,
E = alpha * D ** beta, fitted to rainfall events that triggered dated landslides, then lowered to the chosen exceedance
level (frequentist method, Brunetti et al. 2010). An antecedent precipitation index adds the wetness before the event.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Threshold:
    alpha: float
    beta: float
    level: float  # share of triggering events allowed below the line, such as 0.05
    n_events: int

    def rain_needed(self, duration_days: float) -> float:
        return self.alpha * duration_days ** self.beta

    def exceeds(self, event_mm: float, duration_days: float) -> bool:
        return event_mm >= self.rain_needed(duration_days)


def events(rain_mm: np.ndarray, dry_days: int = 2, wet_mm: float = 1.0) -> list[tuple[int, int, float]]:
    """Rainfall events in a daily series: runs of wet days (at least wet_mm) separated by at least dry_days dry days.
    Returns (start index, end index inclusive, total mm)."""
    r = np.nan_to_num(np.asarray(rain_mm, float))
    wet = r >= wet_mm
    out, i, n = [], 0, len(r)
    while i < n:
        if not wet[i]:
            i += 1
            continue
        start, end, gap = i, i, 0
        j = i + 1
        while j < n:
            if wet[j]:
                end, gap = j, 0
            else:
                gap += 1
                if gap >= dry_days:
                    break
            j += 1
        out.append((start, end, float(r[start:end + 1].sum())))
        i = end + 1
    return out


def fit_ed(event_mm: np.ndarray, duration_days: np.ndarray, level: float = 0.05) -> Threshold:
    """Least squares in log space, then the intercept is lowered so that `level` of the triggering events lie below."""
    e, d = np.asarray(event_mm, float), np.asarray(duration_days, float)
    ok = (e > 0) & (d > 0)
    if ok.sum() < 10:
        raise ValueError(f"{int(ok.sum())} triggering events: too few to fit a threshold (at least 10)")
    x, y = np.log10(d[ok]), np.log10(e[ok])
    beta, intercept = np.polyfit(x, y, 1)
    resid = y - (intercept + beta * x)
    shift = float(np.quantile(resid, level))
    return Threshold(alpha=float(10 ** (intercept + shift)), beta=float(beta), level=level, n_events=int(ok.sum()))


def api(rain_mm: np.ndarray, k: float = 0.9) -> np.ndarray:
    """Antecedent precipitation index: API_t = k * API_(t-1) + P_(t-1), the wetness carried into each day."""
    r = np.nan_to_num(np.asarray(rain_mm, float))
    out = np.zeros_like(r)
    for t in range(1, len(r)):
        out[t] = k * out[t - 1] + r[t - 1]
    return out


def event_at(rain_mm: np.ndarray, t: int, dry_days: int = 2, wet_mm: float = 1.0) -> tuple[float, int] | None:
    """The rainfall event behind day t, from the days up to t only (nothing later is read): the event still running on
    day t, or one that stopped fewer than dry_days days before. Returns (event rainfall in mm, duration in days) or None."""
    ev = events(np.asarray(rain_mm, float)[: t + 1], dry_days, wet_mm)
    if not ev or ev[-1][1] < t - (dry_days - 1):
        return None
    start, end, total = ev[-1]
    return total, end - start + 1


def ongoing(rain_mm: np.ndarray, dry_days: int = 2, wet_mm: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """event_at for every day in one pass: (rainfall so far, duration so far) of the event behind each day, 0 where none.
    Only past and present days are used, so it can run as a monitor."""
    r = np.nan_to_num(np.asarray(rain_mm, float))
    e_out, d_out = np.zeros(len(r)), np.zeros(len(r), dtype=int)
    start = end = None
    total = pending = 0.0
    gap = dry_days
    for t, v in enumerate(r):
        if v >= wet_mm:
            if gap < dry_days and start is not None:  # the event goes on: dry-day drizzle in between counts
                total += pending + v
            else:
                start, total = t, v
            end, gap, pending = t, 0, 0.0
        else:
            gap += 1
            pending += v
        if start is not None and gap < dry_days:
            e_out[t], d_out[t] = total, end - start + 1
    return e_out, d_out


def warnings(rain_mm: np.ndarray, th: Threshold, dry_days: int = 2, wet_mm: float = 1.0) -> np.ndarray:
    """True on each day the event so far reaches the threshold line."""
    e, d = ongoing(rain_mm, dry_days, wet_mm)
    return (d > 0) & (e >= th.alpha * np.maximum(d, 1) ** th.beta)
