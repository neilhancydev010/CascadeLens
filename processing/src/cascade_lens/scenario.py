"""Dam-failure scenario for a glacial lake: what would happen IF the moraine dam breached. Not a prediction of whether or when.

1. Route: the river path from the lake's lowest shore to the edge of the DEM tile, from a depression-filled DEM
   (priority flood, Barnes et al. 2014), so the path crosses flat valley floors instead of getting stuck in pits.
2. Water released: the lake area measured by NISAR times the breach depth (walls taken as vertical, so a slight overestimate).
3. Peak flow at the dam, three published empirical formulas for natural or moraine dams, giving a range:
   Popov (1991) Qp = 0.0048 V^0.896 and Costa and Schuster (1988) Qp = 0.0158 PE^0.41 (PE = breach depth x V x 9800 J)
   give the likely range; Huggel et al. (2002) Qp = 0.00077 V^1.017 is an upper envelope of past floods, shown as the worst case only.
4. Arrival time: at cross-sections cut through the DEM every ~500 m, the flow depth that carries the peak flow is solved from
   Manning's equation, v = R^(2/3) S^(1/2) / n, with roughness n from 0.07 to 0.15. The front is taken to move at the water
   speed v. The peak is not reduced downstream, so the times are on the early (cautious) side.
Everything is a scenario with a range. It is not a hazard map and not a warning.
"""
from __future__ import annotations

import heapq
import json
import pathlib

import numpy as np
import rasterio
from rasterio import features
from rasterio.windows import from_bounds
from scipy import ndimage

STEP = 2                 # DEM averaged 2x2: about 60 m cells, enough for valleys and 4x faster
BREACH_M = (10, 20, 30)  # breach depths tried
N_RANGE = (0.07, 0.15)   # Manning roughness for steep boulder channels carrying debris (Chow 1959 gives 0.05 to 0.15+)
SECTION_EVERY_M = 500
HALF_WIDTH_M = 1500
GAMMA = 9800.0
FORMULAS = {
    "popov": ("Popov (1991)", lambda v, h: 0.0048 * v ** 0.896),
    "huggel": ("Huggel et al. (2002), upper envelope", lambda v, h: 0.00077 * v ** 1.017),
    "costa": ("Costa and Schuster (1988)", lambda v, h: 0.0158 * (h * v * GAMMA) ** 0.41),
}


def _load(dem: pathlib.Path, bounds):
    with rasterio.open(dem) as src:
        w = from_bounds(*bounds, src.transform).round_offsets().round_lengths()
        z = src.read(1, window=w).astype(np.float32)
        t = src.window_transform(w)
    r, c = z.shape[0] // STEP * STEP, z.shape[1] // STEP * STEP
    z = z[:r, :c].reshape(r // STEP, STEP, c // STEP, STEP).mean(axis=(1, 3))
    return z, t * rasterio.Affine.scale(STEP)


def drainage(z: np.ndarray) -> np.ndarray:
    """Priority flood from the edges. Each cell's parent is the neighbour it was reached from, which is where its water goes."""
    R, C = z.shape
    done = np.zeros(R * C, bool)
    parent = np.full(R * C, -1, np.int64)
    fill = z.ravel().copy()
    heap = []
    edge = [(r, c) for r in range(R) for c in (0, C - 1)] + [(r, c) for c in range(1, C - 1) for r in (0, R - 1)]
    for r, c in edge:
        i = r * C + c
        done[i] = True
        heapq.heappush(heap, (float(fill[i]), i))
    nb = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    while heap:
        e, i = heapq.heappop(heap)
        r, c = divmod(i, C)
        for dr, dc in nb:
            rr, cc = r + dr, c + dc
            if 0 <= rr < R and 0 <= cc < C:
                j = rr * C + cc
                if not done[j]:
                    done[j] = True
                    parent[j] = i
                    if fill[j] < e:
                        fill[j] = e
                    heapq.heappush(heap, (float(fill[j]), j))
    return parent


def _km(t, lat0):
    kx = abs(t.a) * 111.32 * np.cos(np.radians(lat0))
    ky = abs(t.e) * 110.57
    return kx, ky


def route_from_lake(z, t, parent, lake_geojson: dict):
    """Start at the lowest cell touching the lake (its natural outlet) and follow the parents to the edge."""
    shapes = [(f["geometry"], 1) for f in lake_geojson["features"]]
    lake = features.rasterize(shapes, out_shape=z.shape, transform=t, all_touched=True).astype(bool)
    shore = ndimage.binary_dilation(lake, iterations=2) & ~lake
    rr, cc = np.nonzero(shore)
    k = int(np.argmin(z[rr, cc]))
    C = z.shape[1]
    i, out = int(rr[k] * C + cc[k]), []
    while i >= 0 and len(out) < 50000:
        out.append(i)
        i = int(parent[i])
    rows, cols = np.divmod(np.array(out), C)
    return rows, cols, lake


def _bilinear(z, r, c):
    r0, c0 = np.clip(np.floor(r).astype(int), 0, z.shape[0] - 2), np.clip(np.floor(c).astype(int), 0, z.shape[1] - 2)
    fr, fc = r - r0, c - c0
    return (z[r0, c0] * (1 - fr) * (1 - fc) + z[r0 + 1, c0] * fr * (1 - fc) + z[r0, c0 + 1] * (1 - fr) * fc + z[r0 + 1, c0 + 1] * fr * fc)


def sections(z, t, rows, cols, lat0):
    """Cross-sections through the DEM, perpendicular to the route, every SECTION_EVERY_M metres."""
    kx, ky = _km(t, lat0)
    xs, ys = cols * kx * 1000, -rows * ky * 1000  # metres, y up
    seg = np.hypot(np.diff(xs), np.diff(ys))
    dist = np.concatenate([[0], np.cumsum(seg)])
    out = []
    for d in np.arange(SECTION_EVERY_M, dist[-1] - SECTION_EVERY_M, SECTION_EVERY_M):
        i = int(np.searchsorted(dist, d))
        a, b = max(0, i - 8), min(len(xs) - 1, i + 8)
        dx, dy = xs[b] - xs[a], ys[b] - ys[a]
        n = np.hypot(dx, dy) or 1
        px, py = -dy / n, dx / n
        s = np.arange(-HALF_WIDTH_M, HALF_WIDTH_M + 1, 30.0)
        cc = cols[i] + s * px / (kx * 1000)
        rr = rows[i] - s * py / (ky * 1000)
        prof = _bilinear(z, rr, cc)
        up = max(0, int(np.searchsorted(dist, d - 1000)))
        dn = min(len(dist) - 1, int(np.searchsorted(dist, d + 1000)))
        zr = z[rows, cols]
        slope = max(0.002, float((zr[up] - zr[dn]) / max(1.0, dist[dn] - dist[up])))
        out.append({"i": i, "km": d / 1000, "s": s, "prof": prof, "slope": slope, "rr": rr, "cc": cc})
    return out


def _hydraulics(sec, q: float, n: float):
    """Depth above the lowest point of the section that carries q, by bisection. Returns depth, speed, wet span."""
    s, prof = sec["s"], sec["prof"]
    mid = len(s) // 2
    bed_i = mid - 10 + int(np.argmin(prof[mid - 10: mid + 11]))
    bed = prof[bed_i]

    def flow(h):
        wet = prof < bed + h
        lab, _ = ndimage.label(wet)
        k = lab == lab[bed_i]
        depth = np.where(k, bed + h - prof, 0)
        area = float(depth.sum() * 30.0)
        width = float(k.sum() * 30.0)
        if area <= 0:
            return 0.0, 0.0, k
        r = area / (width + 2 * h)
        v = r ** (2 / 3) * sec["slope"] ** 0.5 / n
        return area * v, v, k

    lo, hi = 0.01, 200.0
    for _ in range(40):
        h = (lo + hi) / 2
        if flow(h)[0] < q:
            lo = h
        else:
            hi = h
    h = (lo + hi) / 2
    _, v, k = flow(h)
    idx = np.nonzero(k)[0]
    return h, v, (int(idx[0]), int(idx[-1])) if idx.size else (bed_i, bed_i)


def hillshade(z: np.ndarray, t, lat0: float) -> np.ndarray:
    """Grey shading from the north-west, 0 to 1, for a map background over the whole route."""
    kx, ky = _km(t, lat0)
    gy, gx = np.gradient(z, ky * 1000, kx * 1000)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = np.radians(315), np.radians(45)
    return np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1).astype(np.float32)


def run(dem: pathlib.Path, lake_geojson: dict, area_km2: float, centre_lnglat, public: pathlib.Path, case: str, work: pathlib.Path | None = None) -> dict:
    lon, lat = centre_lnglat
    bounds = (np.floor(lon) - 0.0, np.floor(lat), np.floor(lon) + 1.0, np.floor(lat) + 1.0)  # the whole 1 degree tile
    with rasterio.open(dem) as src:
        b = src.bounds
    bounds = (max(b.left, lon - 0.5), max(b.bottom, lat - 0.6), min(b.right, lon + 0.5), min(b.top, lat + 0.15))
    z, t = _load(dem, bounds)
    parent = drainage(z)
    shade_tif = None
    if work:
        from . import export
        shade_tif = export.write_geotiff(work / "hillshade.tif", hillshade(z, t, lat), t, 4326)
    rows, cols, _ = route_from_lake(z, t, parent, lake_geojson)
    secs = sections(z, t, rows, cols, lat)
    lng_lat = lambda r, c: [round(float(v), 5) for v in (t * (c + 0.5, r + 0.5))]  # noqa: E731
    kx, ky = _km(t, lat)
    km = np.concatenate([[0], np.cumsum(np.hypot(np.diff(cols) * kx, np.diff(rows) * ky))])
    area_m2 = area_km2 * 1e6
    scenarios = []
    extent = None
    for depth in BREACH_M:
        v = area_m2 * depth
        peaks = {k: round(f(v, depth)) for k, (_, f) in FORMULAS.items()}
        likely = [peaks["popov"], peaks["costa"]]
        q_lo, q_hi = min(likely), max(likely)
        fast, slow = [0.0], [0.0]
        pts = []
        spans = []
        for sec in secs:
            _, v_fast, span = _hydraulics(sec, q_hi, N_RANGE[0])
            h_slow, v_slow, _ = _hydraulics(sec, q_lo, N_RANGE[1])
            h_fast, _, _ = _hydraulics(sec, q_hi, N_RANGE[1])
            pts.append((sec["km"], v_fast, v_slow, _hydraulics(sec, q_lo, N_RANGE[0])[0], h_fast))
            spans.append(span)
        arrival, depth_m = [], []
        prev = 0.0
        tf = ts = 0.0
        for k_, cf, cs, h, h2 in pts:
            ds = (k_ - prev) * 1000
            tf += ds / max(cf, 0.3)
            ts += ds / max(cs, 0.3)
            prev = k_
            arrival.append([round(k_, 1), round(tf / 60), round(ts / 60)])
            depth_m.append([round(k_, 1), round(h, 1), round(h2, 1)])
        scenarios.append({"breachM": depth, "volumeM3": round(v), "peakM3s": peaks, "peakRange": [q_lo, q_hi], "worstM3s": peaks["huggel"], "arrival": arrival, "depthM": depth_m})
        if depth == 20:  # the middle scenario draws the flooded area: the highest flow, smoothest channel, so the widest
            left, right = [], []
            for sec, (a, b2) in zip(secs, spans):
                left.append(lng_lat(sec["rr"][a], sec["cc"][a]))
                right.append(lng_lat(sec["rr"][b2], sec["cc"][b2]))
            extent = [left + right[::-1] + [left[0]]]
    line = [lng_lat(r, c) for r, c in zip(rows[::2], cols[::2])]
    vec = public / f"vectors/{case}-scenario-route.geojson"
    vec.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"kind": "route"}, "geometry": {"type": "LineString", "coordinates": line}}]}), encoding="utf-8")
    ext = public / f"vectors/{case}-scenario-extent.geojson"
    ext.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"kind": "extent", "breachM": 20}, "geometry": {"type": "Polygon", "coordinates": extent}}] if extent else []}), encoding="utf-8")
    profile = [[round(float(km[i]), 2), round(float(z[rows[i], cols[i]]))] for i in range(0, len(rows), 4)]
    marks = [{"km": round(float(km[i]), 1), "lngLat": lng_lat(rows[i], cols[i])} for i in range(0, len(rows), max(1, len(rows) // 12))]
    return {"routeKm": round(float(km[-1]), 1), "routeEnd": lng_lat(rows[-1], cols[-1]), "lakeAreaKm2": area_km2, "profile": profile, "marks": marks,
            "scenarios": scenarios, "routeVector": vec.relative_to(public.parent).as_posix(), "extentVector": ext.relative_to(public.parent).as_posix(),
            "formulas": {k: n for k, (n, _) in FORMULAS.items()}, "roughness": list(N_RANGE), "sectionEveryM": SECTION_EVERY_M,
            "bounds": [round(float(v), 4) for v in (t.c, t.f + t.e * z.shape[0], t.c + t.a * z.shape[1], t.f)], "_shade": str(shade_tif) if shade_tif else None}
