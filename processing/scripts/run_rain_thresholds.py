"""First real run of the rainfall-trigger threshold model (audit P2, capability L2): IMERG Late against BIPAD landslides.

    python run_rain_thresholds.py      (needs prepare_rainfall.py and prepare_bipad_inventory.py first)

Method, fixed before any test-period score was looked at:
  1. Each BIPAD landslide in area R2 is placed in its 0.1 degree IMERG cell; several reports in one cell on one day count
     once. Its triggering rainfall event is the event running that day, or one that stopped the day before (two dry days
     end an event; a wet day has at least 1 mm). Landslides with no such event are counted and left out of the fit.
  2. E = alpha * D ** beta is fitted to the triggering events (thresholds.fit_ed), lowered so a share `level` of them
     lies below the line.
  3. A cell is over the line on each UTC day its event so far reaches it. The corridor (R1) is warned on a day when at
     least a share of its cells is over the line. Calibration picks the level (0.05, 0.10, 0.20, 0.30, 0.50) and the share
     (any cell, 10%, 25%, 50%) together: fitted on 2016-06-01 to 2022-12-31, scored on 2023-2024 in the corridor. The
     chosen level is refitted on 2016-06-01 to 2024-12-31.
  4. Validation, 2025-01-01 to 2026-10-31, never scored before. A corridor-day with at least one report is an event day.
     Scored as published: IMERG Late appears about 14 h after the UTC day ends (19:45 the next day in Nepal), so a
     warning counts for reports 2 or 3 days after the rainfall day (verify.windowed, leads 2 to 3). The same scores
     without the delay (leads 0 to 1) are recorded as a diagnostic, not as skill. R2 is scored the same way, for context.
  5. The criterion, stated here before scoring: the corridor's CSI as published must beat chance, meaning above the
     95th percentile of 1000 shuffles that keep the number of warning days in each calendar month (p < 0.05).
Cell-by-cell scoring was tried first on the training years and dropped: reports are too sparse per 11 km cell (most
cells have none in a year) for a cell-day to mean anything.
Writes data/metadata/evidence/landslide.L2.{model,calibration,validation}.json and data/qa/rain_thresholds.json.
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys
from datetime import date, datetime, timezone

import numpy as np
import rasterio

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import verify  # noqa: E402
from cascade_lens.models import thresholds as th  # noqa: E402

RAIN = ROOT / "data/reference/rainfall/GPM_3IMERGDL.07"
INVENTORY = ROOT / "data/raw/hazard/bipad/bipad_landslides.csv"
EVIDENCE = ROOT / "data/metadata/evidence"
QA = ROOT / "data/qa"
CATALOGUE = json.loads((ROOT / "processing/configs/readiness.json").read_text(encoding="utf-8"))
R1, R2 = CATALOGUE["areas"]["R1"], CATALOGUE["areas"]["R2"]
START, TRAIN_END, CAL_END, TEST_END = date(2016, 6, 1), date(2022, 12, 31), date(2024, 12, 31), date(2026, 10, 31)
LEVELS = [0.05, 0.10, 0.20, 0.30, 0.50]
SHARES = [0.0, 0.10, 0.25, 0.50]  # share of the corridor's cells over the line for a corridor warning (0: any cell)
PUBLISHED, DIAGNOSTIC = (2, 3), (0, 1)
DRY_DAYS, WET_MM = 2, 1.0


def load_rain() -> tuple[list[date], np.ndarray, rasterio.Affine]:
    """Daily totals in mm as [day, row, col], and the grid transform."""
    days, stacks, transform = [], [], None
    for p in sorted(RAIN.glob("imerg_2*.tif")):
        with rasterio.open(p) as d:
            a = d.read().astype(float)
            a[a == d.nodata] = np.nan
            stacks.append(a * 24.0)
            days += [date.fromisoformat(d.descriptions[i]) for i in range(d.count)]
            transform = d.transform
    return days, np.concatenate(stacks), transform


def load_landslides(days: list[date], transform, shape) -> tuple[np.ndarray, list[dict]]:
    """Boolean [day, row, col] of cell-days with at least one report, and the reports placed on the grid."""
    index = {d: i for i, d in enumerate(days)}
    obs = np.zeros((len(days), *shape), bool)
    placed = []
    for r in csv.DictReader(open(INVENTORY, encoding="utf-8")):
        lon, lat, d = float(r["lon"]), float(r["lat"]), date.fromisoformat(r["date"])
        if not (R2[0] <= lon <= R2[2] and R2[1] <= lat <= R2[3]) or d not in index:
            continue
        col, row = (int(v) for v in ~transform * (lon, lat))
        if 0 <= row < shape[0] and 0 <= col < shape[1]:
            obs[index[d], row, col] = True
            placed.append({"date": d, "row": row, "col": col, "lon": lon, "lat": lat})
    return obs, placed


def cell_mask(transform, shape, box) -> np.ndarray:
    rows, cols = np.indices(shape)
    lon, lat = rasterio.transform.xy(transform, rows.ravel(), cols.ravel())
    lon, lat = np.asarray(lon).reshape(shape), np.asarray(lat).reshape(shape)
    return (lon >= box[0]) & (lon <= box[2]) & (lat >= box[1]) & (lat <= box[3])


def triggers(rain: np.ndarray, obs: np.ndarray, t0: int, t1: int) -> tuple[np.ndarray, np.ndarray, int]:
    """(E, D) of the triggering event of each reported cell-day in [t0, t1], and how many had no rainfall event."""
    e, d, dry = [], [], 0
    for t, r, c in zip(*np.nonzero(obs[t0:t1 + 1])):
        got = th.event_at(rain[: t0 + t + 1, r, c], t0 + t, DRY_DAYS, WET_MM)
        if got is None or got[0] <= 0:
            dry += 1
        else:
            e.append(got[0])
            d.append(got[1])
    return np.array(e), np.array(d), dry


def event_so_far(rain: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """thresholds.ongoing for every cell: rainfall and duration of the event behind each day, from past days only."""
    e, d = np.zeros(rain.shape), np.zeros(rain.shape, dtype=int)
    for r in range(rain.shape[1]):
        for c in range(rain.shape[2]):
            e[:, r, c], d[:, r, c] = th.ongoing(rain[:, r, c], DRY_DAYS, WET_MM)
    return e, d


def warn_grid(e: np.ndarray, d: np.ndarray, threshold: th.Threshold) -> np.ndarray:
    """thresholds.warnings on the whole grid (the same rule, vectorised)."""
    return (d > 0) & (e >= threshold.alpha * np.maximum(d, 1) ** threshold.beta)


def area_series(w: np.ndarray, obs: np.ndarray, mask: np.ndarray, share: float) -> tuple[np.ndarray, np.ndarray]:
    """One area as one place: a warning day when at least `share` of its cells are over the line (any cell when 0), an
    event day when it has at least one report. Returned as [day, 1] arrays for verify.windowed."""
    frac = w[:, mask].mean(axis=1)
    warn = frac > 0 if share == 0 else frac >= share
    return warn[:, None], obs[:, mask].any(axis=1)[:, None]


def score(warn, ev, t0, t1, leads) -> dict:
    sl = slice(t0, t1 + 1)
    c = verify.windowed(warn[sl], ev[sl], *leads)
    return {**c.as_dict(), "warningDays": int(warn[sl].sum()), "eventDays": int(ev[sl].sum()), "days": t1 - t0 + 1}


def main() -> None:
    days, rain, transform = load_rain()
    if days[0] > START or days[-1] < TEST_END:
        raise SystemExit(f"rainfall covers {days[0]} to {days[-1]}; needs {START} to {TEST_END}")
    gaps = [d for a, d in zip(days, days[1:]) if (d - a).days != 1]
    if gaps:  # event runs read neighbouring bands as neighbouring days, so a missing day would join two that are apart
        raise SystemExit(f"{len(gaps)} gaps in the rainfall days, first before {gaps[0]}: rerun fetch_imerg.py and prepare_rainfall.py")
    idx = {d: i for i, d in enumerate(days)}
    obs, placed = load_landslides(days, transform, rain.shape[1:])
    m1, m2 = cell_mask(transform, rain.shape[1:], R1), cell_mask(transform, rain.shape[1:], R2)
    i0, i_tr, i_cal, i_te = idx[START], idx[TRAIN_END], idx[CAL_END], idx[TEST_END]
    e_now, d_now = event_so_far(rain)

    # 1-3. Fit on 2016-2022; choose the level and the share of corridor cells on 2023-2024; refit on 2016-2024
    e_tr, d_tr, dry_tr = triggers(rain, obs, i0, i_tr)
    cal = []
    for level in LEVELS:
        fit = th.fit_ed(e_tr, d_tr, level)
        w = warn_grid(e_now, d_now, fit)
        for share in SHARES:
            warn, ev = area_series(w, obs, m1, share)
            cal.append({"level": level, "share": share, "alpha": round(fit.alpha, 3), "beta": round(fit.beta, 3),
                        "published": score(warn, ev, i_tr + 1, i_cal, PUBLISHED)})
    best = max(cal, key=lambda c: (c["published"]["csi"] or 0, -abs((c["published"]["bias"] or 99) - 1)))
    e_all, d_all, dry_all = triggers(rain, obs, i0, i_cal)
    final = th.fit_ed(e_all, d_all, best["level"])

    # 4-5. The held-out years, never scored before this point
    w = warn_grid(e_now, d_now, final)
    t0 = i_cal + 1
    months = np.array([days[i].year * 12 + days[i].month for i in range(t0, i_te + 1)])
    results = {}
    for name, mask in (("R1", m1), ("R2", m2)):
        warn, ev = area_series(w, obs, mask, best["share"])
        pub = score(warn, ev, t0, i_te, PUBLISHED)
        chance = verify.shuffled_csi(warn[t0:i_te + 1], ev[t0:i_te + 1], months, *PUBLISHED, n=1000, seed=0)
        p95 = float(np.nanpercentile(chance, 95))
        p = float((np.sum(chance >= (pub["csi"] or 0)) + 1) / (len(chance) + 1))
        results[name] = {"cells": int(mask.sum()), "published": pub, "diagnosticNoDelay": score(warn, ev, t0, i_te, DIAGNOSTIC),
                         "chanceCsi": {"median": round(float(np.nanmedian(chance)), 4), "p95": round(p95, 4)}, "pValue": round(p, 4)}
    criterion_met = bool(results["R1"]["published"]["csi"] is not None and results["R1"]["published"]["csi"] > results["R1"]["chanceCsi"]["p95"])

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    common = {"capability": "landslide.L2", "generatedAt": now, "script": "processing/scripts/run_rain_thresholds.py",
              "inputs": {"rainfall": "C5: IMERG Late V07 daily, 0.1 degree (data/reference/rainfall/GPM_3IMERGDL.07)",
                         "inventory": "C1: BIPAD landslide incidents (data/raw/hazard/bipad, licence not established)"},
              "needsDatasets": ["C1", "C5"]}
    r1 = results["R1"]["published"]
    records = {
        "model": {**common, "key": "landslide.L2.model",
                  "summary": (f"Rainfall event-duration threshold E = {final.alpha:.1f} x D^{final.beta:.2f} mm, fitted to {final.n_events} "
                              f"triggering events ({best['level']:.0%} below the line), BIPAD 2016-2024 with IMERG Late"),
                  "threshold": {"alpha": final.alpha, "beta": final.beta, "level": final.level, "nEvents": final.n_events},
                  "rules": {"dryDays": DRY_DAYS, "wetMm": WET_MM}, "reportsWithoutRain": dry_all},
        "calibration": {**common, "key": "landslide.L2.calibration",
                        "summary": (f"Exceedance level {best['level']:.0%} and a corridor warning when {'any cell' if best['share'] == 0 else format(best['share'], '.0%') + ' of cells'} "
                                    f"is over the line, chosen on 2023-2024 (as published: CSI {best['published']['csi']})"),
                        "fittedOn": [START.isoformat(), TRAIN_END.isoformat()], "scoredOn": ["2023-01-01", CAL_END.isoformat()],
                        "candidates": cal, "reportsWithoutRainInFit": dry_tr},
        "validation": {**common, "key": "landslide.L2.validation", "criterionMet": criterion_met,
                       "summary": (f"2025-2026 held out, corridor (R1), as published: POD {r1['pod']}, FAR {r1['far']}, CSI {r1['csi']}; "
                                   f"chance CSI 95th percentile {results['R1']['chanceCsi']['p95']} (p = {results['R1']['pValue']})"),
                       "criterion": ("The corridor's (R1) CSI as published, a warning counting for reports 2 to 3 days after the rainfall day, "
                                     "must exceed the 95th percentile of 1000 shuffles that keep the number of warning days in each calendar month"),
                       "testPeriod": [days[t0].isoformat(), TEST_END.isoformat()], "results": results,
                       "caveats": ["Reports, not landslides: a day with no BIPAD report is not a day without a landslide",
                                   "Report points are ward or municipality reference points, so a cell can be off by one",
                                   "Reporting grew strongly after 2023, so the test period has more reports than the training years",
                                   "IMERG history is the V07 reprocessing, not the values issued at the time"]},
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    for k, rec in records.items():
        (EVIDENCE / f"landslide.L2.{k}.json").write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    QA.mkdir(parents=True, exist_ok=True)
    (QA / "rain_thresholds.json").write_text(json.dumps({"records": records, "reportsPlaced": len(placed),
                                                          "triggers": {"E": e_all.round(1).tolist(), "D": d_all.tolist()}}, indent=1) + "\n",
                                             encoding="utf-8")
    print(records["model"]["summary"])
    print(records["calibration"]["summary"])
    for name, r in results.items():
        print(f"{name} ({r['cells']} cells): published {r['published']}, chance p95 {r['chanceCsi']['p95']}, p {r['pValue']}; "
              f"no delay {r['diagnosticNoDelay']['csi']}")
    print("criterion", "MET" if criterion_met else "NOT MET")


if __name__ == "__main__":
    main()
