"""Coherence inside a mapped zone against nearby control ground, across GUNW pairs of one track and frame.

The question: did coherence drop inside the independently mapped zone across the event, while the ground around it did not?
A drop in both would point at the season or the time gap; a drop inside only is consistent with surface change there. It is
descriptive evidence, not proof of cause.

Choices, each recorded in the output:
- Coherence: unwrappedInterferogram/{pol}/coherenceMagnitude with the product's own mask applied (fill, water and invalid
  subswath excluded), the same dataset and rules as the app's coherence layer and Radar Observability.
- Control: ground between RING_M[0] and RING_M[1] metres outside the zone.
- Uncertainty: neighbouring pixels are strongly correlated, so treating them as independent gives intervals that are far too
  narrow. The 95% interval of each median comes from a spatial block bootstrap: whole BLOCK_M blocks are resampled.
- Comparability: each pair's interval in days and its acquisition mode (the bandwidth field of the file name, plus
  rangeBandwidth when the file states it) are reported, because a longer pair or a different mode changes coherence by itself.
"""
from __future__ import annotations

import re

import h5py
import numpy as np
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import mapping
from shapely.ops import transform as stransform

from . import nisar, quality

METHOD_VERSION = 2
UNW = "/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram"
RING_M = (300.0, 1500.0)
BLOCK_M = 1000.0
N_BOOT = 1000
SEED = 0


def pair_dates(name: str) -> tuple[str, str]:
    d = re.findall(r"_(\d{8})T\d{6}_\d{8}T\d{6}", name)
    if len(d) < 2:
        raise ValueError(f"No reference and secondary dates in {name}")
    iso = lambda s: f"{s[:4]}-{s[4:6]}-{s[6:]}"  # noqa: E731
    return iso(d[0]), iso(d[1])


def mode_token(name: str) -> str | None:
    """The four-digit field after the secondary cycle in a GUNW file name, e.g. 2000 or 4000. It differs between acquisition
    modes; read rangeBandwidth from the file for its physical meaning."""
    m = re.search(r"_GUNW_\d{3}_\d{3}_[AD]_\d{3}_\d{3}_(\d{4})_", name)
    return m.group(1) if m else None


def range_bandwidth_hz(h5) -> float | None:
    found = []

    def visit(name, obj):
        if isinstance(obj, h5py.Dataset) and name.rsplit("/", 1)[-1] == "rangeBandwidth" and "frequencyA" in name:
            found.append(float(np.asarray(obj[()]).ravel()[0]))

    h5["/science/LSAR"].visititems(visit)
    return next((v for v in found if np.isfinite(v) and v > 0), None)


def block_bootstrap_ci(values: np.ndarray, rows: np.ndarray, cols: np.ndarray, block_px: int, n: int, rng: np.random.Generator) -> list[float] | None:
    """95% interval of the median, resampling whole spatial blocks with replacement."""
    if values.size == 0:
        return None
    ids = (rows // block_px).astype(np.int64) * 1_000_003 + (cols // block_px).astype(np.int64)
    order = np.argsort(ids, kind="stable")
    ids, values = ids[order], values[order]
    starts = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    blocks = np.split(values, starts[1:])
    k = len(blocks)
    meds = np.empty(n)
    for i in range(n):
        meds[i] = np.median(np.concatenate([blocks[j] for j in rng.integers(0, k, k)]))
    return [round(float(np.percentile(meds, 2.5)), 3), round(float(np.percentile(meds, 97.5)), 3)]


def pair_stats(path, zone_lonlat, pol: str = "HH", ring_m=RING_M, block_m: float = BLOCK_M, n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    coh_path, mask_path = f"{UNW}/{pol}/coherenceMagnitude", f"{UNW}/mask"
    with h5py.File(path, "r") as h:
        if mask_path not in h:
            raise ValueError(f"{path.name}: no {mask_path}; without the product mask its validity cannot be checked")
        grid = nisar.find_grid(h, coh_path)
        if not grid.same_as(nisar.find_grid(h, mask_path)):
            raise ValueError(f"{path.name}: coherence and mask are not on one grid")
        ident = {k: np.asarray(h[f"/science/LSAR/identification/{k}"][()]).item() for k in ("trackNumber", "frameNumber", "orbitPassDirection")}
        to_utm = Transformer.from_crs(4326, grid.epsg, always_xy=True).transform
        zone = stransform(to_utm, zone_lonlat)
        outer = zone.buffer(ring_m[1])
        x0, y0, x1, y1 = outer.bounds
        c = np.flatnonzero((grid.x >= x0 - abs(grid.dx)) & (grid.x <= x1 + abs(grid.dx)))
        r = np.flatnonzero((grid.y >= y0 - abs(grid.dy)) & (grid.y <= y1 + abs(grid.dy)))
        if not c.size or not r.size:
            raise ValueError(f"{path.name}: the zone does not overlap this frame")
        win = np.s_[r[0]:r[-1] + 1, c[0]:c[-1] + 1]
        coh = h[coh_path][win].astype(np.float64)
        mask = h[mask_path][win]
        bw = range_bandwidth_hz(h)
    tr = grid.transform(r[0], c[0])
    shape = coh.shape
    burn = lambda g: rasterize([mapping(g)], out_shape=shape, transform=tr).astype(bool)  # noqa: E731
    in_zone = burn(zone)
    in_ring = burn(outer) & ~burn(zone.buffer(ring_m[0]))
    md = quality.decode_gunw_mask(mask)
    with np.errstate(invalid="ignore"):
        valid = np.isfinite(coh) & (coh > 0) & ~(md["fill"] | md["unusable"])
    block_px = max(1, int(round(block_m / abs(grid.dx))))
    rng = np.random.default_rng(seed)
    out = {}
    for key, zmask in (("inside", in_zone), ("outside", in_ring)):
        ok = zmask & valid
        rr, cc = np.nonzero(ok)
        v = coh[ok]
        out[key] = round(float(np.median(v)), 3) if v.size else None
        out[f"{key}Ci95"] = block_bootstrap_ci(v, rr, cc, block_px, n_boot, rng)
        out[f"{key}ValidPct"] = round(100 * float(ok.sum()) / max(1, int(zmask.sum())), 1)
    t1, t2 = pair_dates(path.name)
    return {"pair": [t1, t2], "days": int((np.datetime64(t2) - np.datetime64(t1)).astype(int)), **out, "validPct": out["insideValidPct"],
            "granule": path.stem, "mode": mode_token(path.name), "rangeBandwidthHz": bw, "postingM": abs(grid.dx),
            "track": int(ident["trackNumber"]), "frame": int(ident["frameNumber"]),
            "direction": ident["orbitPassDirection"].decode() if isinstance(ident["orbitPassDirection"], bytes) else str(ident["orbitPassDirection"])}


def series(files, zone_lonlat, zone_name: str, event_date: str, **kw) -> dict:
    """One record per pair, sorted by date. All pairs must share track and frame."""
    pairs = sorted((pair_stats(p, zone_lonlat, **kw) for p in files), key=lambda s: s["pair"])
    if not pairs:
        raise ValueError("No GUNW pairs given")
    tf = {(p["track"], p["frame"]) for p in pairs}
    if len(tf) > 1:
        raise ValueError(f"Pairs from different tracks or frames cannot form one series: {sorted(tf)}")
    ring = kw.get("ring_m", RING_M)
    return {"zone": zone_name, "control": f"ground {ring[0]:.0f} to {ring[1]:.0f} m outside the extent", "track": pairs[0]["track"], "frame": pairs[0]["frame"],
            "direction": pairs[0]["direction"].upper(), "eventDate": event_date, "methodVersion": METHOD_VERSION,
            "coherenceDataset": f"{UNW}/{kw.get('pol', 'HH')}/coherenceMagnitude, product mask applied",
            "ciMethod": f"Spatial block bootstrap of the median: {kw.get('block_m', BLOCK_M):.0f} m blocks, {kw.get('n_boot', N_BOOT)} resamples, seed {kw.get('seed', SEED)}",
            "generator": "processing/scripts/prepare_control_series.py", "pairs": pairs}
