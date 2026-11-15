"""Describe a processed pair against the independent UNOSAT polygons. Writes data/qa/<group>-analysis.json.

usage: python analyse_pair.py [pair-a]

Descriptive statistics only. A difference inside a polygon is evidence to examine, not proof of a cause.
"""
import json
import pathlib
import sys

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask

ROOT = pathlib.Path(__file__).resolve().parents[2]
group = sys.argv[1] if len(sys.argv) > 1 else "pair-a"
VEC = ROOT / "frontend/public/data/vectors"
ZONES = {"mapped extent": "unosat_mudflow_extent", "detachment zone": "unosat_detachment_zone", "barrier lakes": "unosat_barrier_lakes"}
VALID, MASKED = 1, 2


def load(frame, mid):
    d = ROOT / "data/processed" / group / frame
    with rasterio.open(d / f"{mid}.tif") as a, rasterio.open(d / f"{mid}.validity.tif") as v:
        return a.read(1), v.read(1), a.transform, a.crs, a.shape


def zone_masks(transform, crs, shape):
    out = {}
    for name, file in ZONES.items():
        g = gpd.read_file(VEC / f"{file}.geojson").to_crs(crs)
        inside = ~geometry_mask(list(g.geometry), shape, transform)
        out[name] = inside
        if name == "mapped extent":  # Nearby terrain for comparison: within 1 km of the extent, outside it
            ring = ~geometry_mask(list(g.geometry.buffer(1000)), shape, transform) & ~inside
            out["1 km ring outside extent"] = ring
    return out


def summary(a, cls, zone):
    n = int(zone.sum())
    if not n:
        return {"pixels": 0}
    ok = zone & (cls == VALID)
    v = a[ok]
    q = (lambda p: round(float(np.percentile(v, p)), 3)) if v.size else (lambda p: None)
    return {"pixels": n, "validPct": round(100 * ok.sum() / n, 1), "maskedPct": round(100 * (zone & (cls == MASKED)).sum() / n, 1), "p25": q(25), "median": q(50), "p75": q(75)}


def frames():
    return sorted(p.name for p in (ROOT / "data/processed" / group).iterdir() if p.is_dir())


report = {"group": group, "note": "Descriptive only. Differences are evidence to examine, not proof of cause.", "frames": {}}
for frame in frames():
    gunw = (ROOT / "data/processed" / group / frame / "gunw-coherence.tif").exists()
    _, _, tr, crs, shape = load(frame, "gunw-coherence" if gunw else "goff-snr")
    zones = zone_masks(tr, crs, shape)
    r = {"shape": list(shape), "crs": str(crs), "zones": {}}
    for mid in (("gunw-coherence",) if gunw else ()) + ("goff-snr", "goff-peak"):
        a, cls, *_ = load(frame, mid)
        r["zones"][mid] = {k: summary(a, cls, z) for k, z in zones.items()}
    for mid in ("goff-range", "goff-azimuth"):
        a, cls, *_ = load(frame, mid)
        med = np.nanmedian(a[cls == VALID])
        r["zones"][mid + " |x - scene median|"] = {k: summary(np.abs(a - med), cls, z) for k, z in zones.items()}
        r.setdefault("sceneMedian", {})[mid] = round(float(med), 3)
        r.setdefault("maskedPct", {})[mid] = round(100 * float((cls == MASKED).mean()), 2)
    if not gunw:
        report["frames"][frame] = r
        continue
    ph, ph_cls, *_ = load(frame, "gunw-phase")
    r["phase"] = {k: summary(ph, ph_cls, z) for k, z in zones.items()}
    ion, ion_cls, *_ = load(frame, "gunw-iono")
    both = (ph_cls == VALID) & (ion_cls == VALID)
    p, i = ph[both], ion[both]
    r["ionosphere"] = {"pixels": int(both.sum()), "pearsonR": round(float(np.corrcoef(p, i)[0, 1]), 3), "stdPhase": round(float(p.std()), 2), "stdIono": round(float(i.std()), 2),
                       "stdPhaseMinusIono": round(float((p - i).std()), 2), "stdPhasePlusIono": round(float((p + i).std()), 2)}
    cc, cc_cls, *_ = load(frame, "gunw-cc")
    labels, counts = np.unique(cc[cc_cls == VALID], return_counts=True)
    r["components"] = {int(a): int(b) for a, b in zip(labels[:12], counts[:12])}
    report["frames"][frame] = r
out = ROOT / "data/qa" / f"{group}-analysis.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=1), encoding="utf-8")
print(json.dumps(report, indent=0)[:6000])
