"""GR4J daily rainfall-runoff model (Perrin, Michel and Andreassian 2003) with a one-band degree-day snow routine, the
lumped conceptual model the audit proposes for F3 on the Trishuli main stem. Four GR4J parameters:

  x1  production store capacity (mm)        x3  routing store capacity (mm)
  x2  groundwater exchange (mm/day)         x4  unit hydrograph time base (days)

and two snow parameters: ddf, the degree-day melt factor (mm per degree C per day), and t_melt (degrees C). Precipitation
falls as snow at or below t_melt. One elevation band only: the Trishuli catchment spans 500 to over 7000 m, so a real
application needs elevation bands and glacier melt, and calibration against DHM discharge before anything is claimed.
"""
from __future__ import annotations

import math

import numpy as np

BOUNDS = {"x1": (10.0, 2500.0), "x2": (-10.0, 5.0), "x3": (5.0, 600.0), "x4": (0.6, 10.0), "ddf": (0.5, 10.0), "t_melt": (-3.0, 3.0)}


def _sh1(t: float, x4: float) -> float:
    return 0.0 if t <= 0 else 1.0 if t >= x4 else (t / x4) ** 2.5


def _sh2(t: float, x4: float) -> float:
    if t <= 0:
        return 0.0
    if t < x4:
        return 0.5 * (t / x4) ** 2.5
    if t < 2 * x4:
        return 1 - 0.5 * (2 - t / x4) ** 2.5
    return 1.0


def unit_hydrographs(x4: float) -> tuple[np.ndarray, np.ndarray]:
    n1, n2 = int(math.ceil(x4)), int(math.ceil(2 * x4))
    uh1 = np.array([_sh1(j, x4) - _sh1(j - 1, x4) for j in range(1, n1 + 1)])
    uh2 = np.array([_sh2(j, x4) - _sh2(j - 1, x4) for j in range(1, n2 + 1)])
    return uh1, uh2


def snow(precip: np.ndarray, temp: np.ndarray, ddf: float, t_melt: float) -> tuple[np.ndarray, np.ndarray]:
    """Liquid water reaching the ground each day, and the snowpack (mm water equivalent)."""
    pack, liquid, packs = 0.0, np.zeros(len(precip)), np.zeros(len(precip))
    for t, (p, tc) in enumerate(zip(precip, temp)):
        if tc <= t_melt:
            pack += p
            water = 0.0
        else:
            water = p
        melt = min(pack, ddf * max(0.0, tc - t_melt))
        pack -= melt
        liquid[t], packs[t] = water + melt, pack
    return liquid, packs


def run(precip: np.ndarray, pet: np.ndarray, x1: float, x2: float, x3: float, x4: float, temp: np.ndarray | None = None,
        ddf: float = 3.0, t_melt: float = 0.0, s0: float = 0.5, r0: float = 0.5, return_states: bool = False):
    """Discharge in mm/day. s0 and r0 are the initial store fillings as fractions of x1 and x3; use a warm-up year."""
    p = np.nan_to_num(np.asarray(precip, float))
    e = np.nan_to_num(np.asarray(pet, float))
    if temp is not None:
        p, _ = snow(p, np.asarray(temp, float), ddf, t_melt)
    uh1, uh2 = unit_hydrographs(x4)
    q9 = np.zeros(len(uh1))
    q1 = np.zeros(len(uh2))
    s, r = s0 * x1, r0 * x3
    out = np.zeros(len(p))
    states = np.zeros((len(p), 2))
    for t in range(len(p)):
        if p[t] >= e[t]:
            pn, en = p[t] - e[t], 0.0
        else:
            pn, en = 0.0, e[t] - p[t]
        ps = es = 0.0
        if pn > 0:
            tw = math.tanh(pn / x1)
            ps = x1 * (1 - (s / x1) ** 2) * tw / (1 + s / x1 * tw)
        if en > 0:
            tw = math.tanh(en / x1)
            es = s * (2 - s / x1) * tw / (1 + (1 - s / x1) * tw)
        s = s - es + ps
        perc = s * (1 - (1 + (4 / 9 * s / x1) ** 4) ** -0.25)
        s -= perc
        pr = perc + (pn - ps)
        q9 = np.roll(q9, -1); q9[-1] = 0.0
        q1 = np.roll(q1, -1); q1[-1] = 0.0
        q9 += 0.9 * pr * uh1
        q1 += 0.1 * pr * uh2
        f = x2 * (r / x3) ** 3.5
        r = max(0.0, r + q9[0] + f)
        qr = r * (1 - (1 + (r / x3) ** 4) ** -0.25)
        r -= qr
        qd = max(0.0, q1[0] + f)
        out[t] = qr + qd
        states[t] = (s, r)
    return (out, states) if return_states else out


def to_m3s(q_mm_day: np.ndarray, area_km2: float) -> np.ndarray:
    return np.asarray(q_mm_day) * area_km2 * 1000 / 86400


def calibrate(precip, pet, q_obs, temp=None, warmup: int = 365, fit_snow: bool = False, seed: int = 0, maxiter: int = 60) -> dict:
    """Maximise NSE over the days after warm-up with differential evolution (fixed seed, so the result is reproducible)."""
    from scipy.optimize import differential_evolution

    from .. import verify
    names = ["x1", "x2", "x3", "x4"] + (["ddf", "t_melt"] if fit_snow else [])
    obs = np.asarray(q_obs, float)

    def loss(v):
        kw = dict(zip(names, v))
        sim = run(precip, pet, kw["x1"], kw["x2"], kw["x3"], kw["x4"], temp, kw.get("ddf", 3.0), kw.get("t_melt", 0.0))
        score = verify.nse(sim[warmup:], obs[warmup:])
        return 1e3 if not np.isfinite(score) else 1 - score

    res = differential_evolution(loss, [BOUNDS[n] for n in names], seed=seed, maxiter=maxiter, tol=1e-6, polish=True)
    params = dict(zip(names, (float(x) for x in res.x)))
    return {"params": params, "nse": round(1 - float(res.fun), 4), "warmupDays": warmup, "evaluations": int(res.nfev)}
