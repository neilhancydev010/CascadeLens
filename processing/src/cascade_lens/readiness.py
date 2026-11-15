"""Readiness engine (audit P1): decides, from the data actually on disk, what state each flood and landslide capability has
earned. The app shows a capability only at that state, with the reasons and the next requirement.

Every raw dataset folder carries a SOURCE.json (see write_source). A capability lists the datasets it needs, each with the
conditions it must meet; then the model, calibration, validation and operational evidence it needs. The state is the
first rung of the ladder that is not met:

  NOT AVAILABLE                         an essential dataset is missing
  DATA AVAILABLE, PROCESSING REQUIRED   every essential dataset is present, but one fails a condition (coverage, units ...)
  MODEL REQUIRED                        the data is fit for use, but no model output is registered
  CALIBRATION REQUIRED                  a model output exists, with no calibration record
  VALIDATION REQUIRED                   calibrated, but no independent validation record, its validation data is missing, or
                                        the validation ran and missed the criterion it stated beforehand ("criterionMet": false)
  EXPERIMENTAL                          validated out of sample, with its metrics recorded; not yet evaluated in operation
  OPERATIONALLY EVALUATED               a full season evaluated with partners

Nothing here runs a model or judges skill: it only checks that the evidence exists and is fit for the claim.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

STATES = ["NOT AVAILABLE", "DATA AVAILABLE, PROCESSING REQUIRED", "MODEL REQUIRED", "CALIBRATION REQUIRED",
          "VALIDATION REQUIRED", "EXPERIMENTAL", "OPERATIONALLY EVALUATED"]
CONTEXT = "CONTEXT ONLY"  # a context capability whose data is fit: it shows where things are, and never predicts

SOURCE_FIELDS = ("dataset", "provider", "product", "version", "url_or_request_ref", "licence", "retrieved_at", "available_at",
                 "spatial_extent", "time_extent", "variables", "units", "crs", "resolution_m", "missing_fraction",
                 "quality_flags", "maturity", "notes")


def write_source(folder: pathlib.Path, **meta) -> pathlib.Path:
    """SOURCE.json beside a raw dataset. available_at (when the provider published it) is what keeps a backtest from reading
    data that did not exist at the forecast issue time."""
    unknown = set(meta) - set(SOURCE_FIELDS)
    if unknown:
        raise ValueError(f"unknown SOURCE.json fields: {sorted(unknown)}")
    if not meta.get("dataset"):
        raise ValueError("SOURCE.json needs the catalogue dataset ID it provides")
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / "SOURCE.json"
    p.write_text(json.dumps({k: meta.get(k) for k in SOURCE_FIELDS}, indent=1), encoding="utf-8")
    return p


def load_sources(*roots: pathlib.Path) -> dict[str, list[dict]]:
    """Every SOURCE.json under the given roots, grouped by the dataset ID it declares."""
    out: dict[str, list[dict]] = {}
    for root in roots:
        for p in sorted(pathlib.Path(root).rglob("SOURCE.json")):
            meta = json.loads(p.read_text(encoding="utf-8"))
            meta["_path"] = p.as_posix()
            out.setdefault(meta["dataset"], []).append(meta)
    return out


def _overlaps(a, b) -> bool:
    return a is not None and b is not None and a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _covers(have, need) -> bool:
    """Time extent [start, end] as ISO dates; the dataset must cover the whole window."""
    return have is not None and need is not None and have[0] <= need[0] and have[1] >= need[1]


def _when(s: str | None) -> datetime | None:
    if not s:
        return None
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def check_dataset(need: dict, meta: dict | None, areas: dict, windows: dict, now: datetime) -> list[dict]:
    """The audit's conditions for one dataset: present, variables, units, spatial overlap, temporal coverage, resolution, CRS,
    missing values, quality flags, freshness, maturity, licence. Each check says ok or not, and why."""
    def c(id_, ok, why):
        return {"id": f"{need['dataset']}.{id_}", "ok": bool(ok), "reason": why}

    if meta is None:
        return [c("present", False, f"{need['dataset']} ({need['name']}) is not on disk")]
    out = [c("present", True, f"Found at {meta['_path']}")]
    have_vars = set(meta.get("variables") or [])
    missing_vars = [v for v in need.get("variables", []) if v not in have_vars]
    out.append(c("variables", not missing_vars, f"Missing variables: {', '.join(missing_vars)}" if missing_vars else "All needed variables present"))
    units = meta.get("units") or {}
    bad_units = [f"{v} in {units.get(v)!r}, needs {u!r}" for v, u in (need.get("units") or {}).items() if units.get(v) != u]
    out.append(c("units", not bad_units, "; ".join(bad_units) if bad_units else "Units as needed"))
    if need.get("area"):
        area = areas[need["area"]]
        out.append(c("space", _overlaps(meta.get("spatial_extent"), area), f"Extent {meta.get('spatial_extent')} against area {need['area']} {area}"))
    if need.get("window"):
        win = windows[need["window"]]
        out.append(c("time", _covers(meta.get("time_extent"), win), f"Time {meta.get('time_extent')} against window {need['window']} {win}"))
    if need.get("maxResolutionM"):
        r = meta.get("resolution_m")
        out.append(c("resolution", r is not None and r <= need["maxResolutionM"], f"Resolution {r} m, needs {need['maxResolutionM']} m or finer"))
    if need.get("crs", True):
        out.append(c("crs", bool(meta.get("crs")), f"CRS {meta.get('crs') or 'not recorded'}"))
    if need.get("maxMissingFraction") is not None:
        mf = meta.get("missing_fraction")
        out.append(c("missing", mf is not None and mf <= need["maxMissingFraction"], f"Missing fraction {mf}, at most {need['maxMissingFraction']}"))
    if need.get("qualityFlags"):
        out.append(c("quality", bool(meta.get("quality_flags")), "Quality flags recorded" if meta.get("quality_flags") else "No quality flags recorded"))
    if need.get("freshDays") is not None:
        av = _when(meta.get("available_at"))
        age = None if av is None else (now - av).days
        out.append(c("fresh", age is not None and age <= need["freshDays"], f"Available {age} days ago, needs {need['freshDays']} or fewer" if age is not None else "No available_at recorded"))
    if need.get("maturity"):
        out.append(c("maturity", meta.get("maturity") in need["maturity"], f"Maturity {meta.get('maturity')!r}, needs one of {need['maturity']}"))
    lic = str(meta.get("licence") or "")
    known = bool(lic) and not any(w in lic.lower() for w in ("not stated", "unknown", "unclear", "not specified"))
    out.append(c("licence", known, f"Licence {lic}" if known else f"Licence not established ({lic or 'not recorded'}): confirm the terms before use"))
    return out


def assess(cap: dict, sources: dict[str, list[dict]], catalogue: dict, evidence: dict[str, dict], now: datetime) -> dict:
    """The state one capability has earned, every check behind it, and the single next requirement."""
    areas, windows, datasets = catalogue["areas"], catalogue["windows"], catalogue["datasets"]
    checks, essential_missing, unfit, partial = [], [], [], []
    for req in cap.get("needs", []):
        need = {**datasets[req["dataset"]], **req, "dataset": req["dataset"]}
        best = None
        for meta in sources.get(req["dataset"], []):  # with several copies, the one that passes the most checks is used
            cs = check_dataset(need, meta, areas, windows, now)
            if best is None or sum(x["ok"] for x in cs) > sum(x["ok"] for x in best):
                best = cs
        cs = best or check_dataset(need, None, areas, windows, now)
        checks += cs
        if not cs[0]["ok"]:
            (essential_missing if req.get("essential", True) else partial).append(req["dataset"])
        elif not all(x["ok"] for x in cs):
            (unfit if req.get("essential", True) else partial).append(req["dataset"])
    if cap.get("context"):  # context capabilities stop at their data: there is no model to earn
        state = "NOT AVAILABLE" if essential_missing else "DATA AVAILABLE, PROCESSING REQUIRED" if unfit else CONTEXT
        nxt = (essential_missing or unfit or partial or [None])[0]
        return {"capability": cap["id"], "name": cap["name"], "family": cap["family"], "state": state, "checks": checks,
                "partial": [f"{d}: {datasets[d]['name']}" for d in partial],
                "next_requirement": None if nxt is None else f"{nxt}: {datasets[nxt]['name']}", "decision": cap.get("decision"), "ceiling": None}
    # Model, calibration, validation and operational evidence are registered records (files written by the model code)
    rungs = [("model", "MODEL REQUIRED"), ("calibration", "CALIBRATION REQUIRED"), ("validation", "VALIDATION REQUIRED"), ("operational", "EXPERIMENTAL")]
    for key, state_if_missing in rungs:
        ev = evidence.get(f"{cap['id']}.{key}")
        has_data = ev is not None and all(sources.get(d) for d in (ev.get("needsDatasets") or []))
        failed = has_data and ev.get("criterionMet") is False  # a record that ran and missed its own stated criterion
        ok = has_data and not failed
        reason = (f"Ran, and missed its criterion: {ev.get('summary', '')}" if failed else ev.get("summary", "Recorded") if ok
                  else f"No {key} record" if ev is None else f"The {key} record needs {', '.join(ev.get('needsDatasets') or [])} on disk")
        checks.append({"id": f"{cap['id']}.{key}", "ok": ok, "reason": reason})
    if essential_missing:
        state = "NOT AVAILABLE"
        nxt = essential_missing[0]
    elif unfit:
        state = "DATA AVAILABLE, PROCESSING REQUIRED"
        nxt = unfit[0]
    else:
        state, nxt = "OPERATIONALLY EVALUATED", None
        for key, state_if_missing in rungs:
            if not next(x for x in checks if x["id"] == f"{cap['id']}.{key}")["ok"]:
                state, nxt = state_if_missing, cap.get("next", {}).get(key, key)
                break
    if cap.get("ceiling") and STATES.index(state) > STATES.index(cap["ceiling"]):
        state = cap["ceiling"]  # some capabilities may never be claimed beyond a level, whatever is on disk
    nxt_text = None if nxt is None else (f"{nxt}: {datasets[nxt]['name']}" if nxt in datasets else nxt)
    return {"capability": cap["id"], "name": cap["name"], "family": cap["family"], "state": state, "checks": checks,
            "partial": [f"{d}: {datasets[d]['name']}" for d in partial], "next_requirement": nxt_text,
            "decision": cap.get("decision"), "ceiling": cap.get("ceiling")}


def run(catalogue: dict, sources: dict[str, list[dict]], evidence: dict[str, dict], now: datetime) -> dict:
    return {"generatedAt": now.isoformat(timespec="seconds"), "states": STATES + [CONTEXT],
            "areas": catalogue["areas"], "windows": catalogue["windows"],
            "capabilities": [assess(c, sources, catalogue, evidence, now) for c in catalogue["capabilities"]]}
