"""Dam-failure scenario for a glacial lake: what would happen IF the moraine dam breached. Not a prediction of whether or when.

1. Route: the river path from the lake's lowest shore to the edge of the DEM tile, from a depression-filled DEM
   (priority flood, Barnes et al. 2014), so the path crosses flat valley floors instead of getting stuck in pits.
2. Water released: the lake area measured by NISAR times the breach depth (walls taken as vertical, so a slight overestimate).
3. Peak flow at the dam, three published empirical formulas for natural or moraine dams, giving a range:
   Popov (1991) Qp = 0.0048 V^0.896 and Costa and Schuster (1988) Qp = 0.0158 PE^0.41 (PE = breach depth x V x 9800 J)
   give the likely range; Huggel et al. (2002) Qp = 0.00077 V^1.017 is an upper envelope of past floods, shown as the worst case only.
4. Arrival time: at cross-sections cut through the DEM every ~500 m, the flow depth that carries the peak flow is solved from
   Manning's equation, v = R^(2/3) S^(1/2) / n, with roughness n from 0.07 to 0.15. The front is taken to move at the water
   speed v. Two simplifications pull the times in opposite directions: a flood wave front travels faster than the water
   (about 5/3 v in a wide channel, which would make every time 40% shorter), and the peak is not reduced downstream
   (a real peak shrinks and slows as it spreads, which would make far times later). Neither is corrected; the kinematic-wave
   times are reported beside the main ones as a sensitivity line only.
5. The lake area carries its own range: the volume and peaks are computed for the lowest, mean and highest area the NISAR
   method allows, and the fastest arrival pairs the highest area with the higher peak formula and the smoothest channel,
   the slowest the lowest area with the lower formula and the roughest channel.
Every cross-section is written out (data/qa/<case>-scenario-sections.csv) so the times can be rebuilt by hand.
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
SLOPE_FLOOR = 0.002      # bed slope never taken below this, so flat DEM stretches cannot stop the water
SPEED_FLOOR = 0.3        # m/s, the front never taken slower than this
KINEMATIC = 5 / 3        # wide-channel Manning: a flood wave moves at c = 5/3 v. Sensitivity only, not the default
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
        raw = float((zr[up] - zr[dn]) / max(1.0, dist[dn] - dist[up]))
        slope = max(SLOPE_FLOOR, raw)
        out.append({"i": i, "km": d / 1000, "s": s, "prof": prof, "slope": slope, "slopeRaw": raw, "slopeFloor": raw < SLOPE_FLOOR, "rr": rr, "cc": cc})
    return out


def section_flow(sec, q: float, n: float) -> dict:
    """The depth above the section's lowest point that carries q, by bisection, with everything a hand check needs:
    bed height, depth h, wetted top width, flow area, hydraulic radius R = area / (width + 2h), speed v and the wet span."""
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
            return 0.0, 0.0, k, 0.0, 0.0, 0.0
        r = area / (width + 2 * h)
        v = r ** (2 / 3) * sec["slope"] ** 0.5 / n
        return area * v, v, k, area, width, r

    lo, hi = 0.01, 200.0
    for _ in range(40):
        h = (lo + hi) / 2
        if flow(h)[0] < q:
            lo = h
        else:
            hi = h
    h = (lo + hi) / 2
    _, v, k, area, width, r = flow(h)
    idx = np.nonzero(k)[0]
    return {"bed": float(bed), "h": h, "v": v, "width": width, "area": area, "R": r,
            "span": (int(idx[0]), int(idx[-1])) if idx.size else (bed_i, bed_i)}


def _hydraulics(sec, q: float, n: float):
    """Depth above the lowest point of the section that carries q. Returns depth, speed, wet span."""
    f = section_flow(sec, q, n)
    return f["h"], f["v"], f["span"]


def volume_and_peaks(area_km2: float, breach_m: float) -> tuple[float, dict]:
    """Released volume V = A x h (m3) and the peak flow at the dam from each formula (m3/s), unrounded."""
    v = area_km2 * 1e6 * breach_m
    return v, {k: f(v, breach_m) for k, (_, f) in FORMULAS.items()}


def travel(secs, q: float, n: float) -> list[dict]:
    """Walk the front down the sections at speed max(v, SPEED_FLOOR). One row per section with the hand-check numbers."""
    rows, prev, cum = [], 0.0, 0.0
    for sec in secs:
        f = section_flow(sec, q, n)
        seg = (sec["km"] - prev) * 1000
        speed = max(f["v"], SPEED_FLOOR)
        t = seg / speed
        cum += t
        prev = sec["km"]
        rows.append({**f, "q": q, "n": n, "speedFloor": f["v"] < SPEED_FLOOR, "segM": seg, "segS": t, "cumS": cum})
    return rows


SECTION_COLUMNS = ["breach_m", "km", "bed_m", "slope_raw", "slope_S", "slope_floor_applied"] + [
    f"{b}_{c}" for b in ("fast", "slow") for c in ("Q_m3s", "n", "h_m", "width_m", "area_m2", "R_m", "v_ms", "speed_floor_applied", "seg_m", "seg_s", "cum_s", "cum_min")]


def section_rows(breach_m: float, secs, fast: list[dict], slow: list[dict]) -> list[list]:
    out = []
    for sec, f, w in zip(secs, fast, slow):
        row = [breach_m, round(sec["km"], 3), round(f["bed"], 2), round(sec["slopeRaw"], 6), round(sec["slope"], 6), int(sec["slopeFloor"])]
        for b in (f, w):
            row += [round(b["q"], 1), b["n"], round(b["h"], 3), round(b["width"], 1), round(b["area"], 1), round(b["R"], 4), round(b["v"], 4),
                    int(b["speedFloor"]), round(b["segM"], 3), round(b["segS"], 2), round(b["cumS"], 3), round(b["cumS"] / 60, 6)]
        out.append(row)
    return out


def hillshade(z: np.ndarray, t, lat0: float) -> np.ndarray:
    """Grey shading from the north-west, 0 to 1, for a map background over the whole route."""
    kx, ky = _km(t, lat0)
    gy, gx = np.gradient(z, ky * 1000, kx * 1000)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = np.radians(315), np.radians(45)
    return np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1).astype(np.float32)


def run(dem: pathlib.Path, lake_geojson: dict, area_km2: float, centre_lnglat, public: pathlib.Path, case: str, work: pathlib.Path | None = None,
        area_range: tuple[float, float] | None = None, sections_csv: pathlib.Path | None = None) -> dict:
    """area_km2 is the mean lake area; area_range the (lowest, highest) area the NISAR method allows. Without a range the mean is used for both."""
    lon, lat = centre_lnglat
    a_lo, a_hi = area_range or (area_km2, area_km2)
    areas = {"low": a_lo, "mean": area_km2, "high": a_hi}
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
    scenarios = []
    extent = None
    table = []
    for depth in BREACH_M:
        vols, peaks = {}, {}
        for name, a in areas.items():
            vols[name], peaks[name] = volume_and_peaks(a, depth)
        # The likely range: the lower of Popov and Costa at the lowest area, to the higher of the two at the highest area
        q_lo = min(peaks["low"]["popov"], peaks["low"]["costa"])
        q_hi = max(peaks["high"]["popov"], peaks["high"]["costa"])
        fast = travel(secs, q_hi, N_RANGE[0])   # highest flow, smoothest channel
        slow = travel(secs, q_lo, N_RANGE[1])   # lowest flow, roughest channel
        shallow = [section_flow(sec, q_lo, N_RANGE[0])["h"] for sec in secs]
        deep = [section_flow(sec, q_hi, N_RANGE[1])["h"] for sec in secs]
        table += section_rows(depth, secs, fast, slow)
        arrival = [[round(sec["km"], 1), round(f["cumS"] / 60), round(w["cumS"] / 60)] for sec, f, w in zip(secs, fast, slow)]
        kinematic = [[round(sec["km"], 1), round(f["cumS"] / KINEMATIC / 60), round(w["cumS"] / KINEMATIC / 60)] for sec, f, w in zip(secs, fast, slow)]
        depth_m = [[round(sec["km"], 1), round(h1, 1), round(h2, 1)] for sec, h1, h2 in zip(secs, shallow, deep)]
        rnd = lambda d: {k: round(v) for k, v in d.items()}  # noqa: E731
        scenarios.append({"breachM": depth, "volumeM3": round(vols["mean"]), "volumeRangeM3": [round(vols["low"]), round(vols["high"])],
                          "peakM3s": rnd(peaks["mean"]), "peaksByArea": {k: rnd(v) for k, v in peaks.items()},
                          "peakRange": [round(q_lo), round(q_hi)], "worstM3s": round(peaks["high"]["huggel"]),
                          "arrival": arrival, "arrivalKinematic": kinematic, "depthM": depth_m,
                          "floors": {"sections": len(secs), "slope": sum(1 for s_ in secs if s_["slopeFloor"]),
                                     "speedFast": sum(1 for f in fast if f["speedFloor"]), "speedSlow": sum(1 for w in slow if w["speedFloor"])}})
        if depth == 20:  # the middle scenario draws the flooded area: the highest flow, smoothest channel, so the widest
            left, right = [], []
            for sec, f in zip(secs, fast):
                a, b2 = f["span"]
                left.append(lng_lat(sec["rr"][a], sec["cc"][a]))
                right.append(lng_lat(sec["rr"][b2], sec["cc"][b2]))
            extent = [left + right[::-1] + [left[0]]]
    if sections_csv:
        import csv
        sections_csv.parent.mkdir(parents=True, exist_ok=True)
        with sections_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(SECTION_COLUMNS)
            w.writerows(table)
    line = [lng_lat(r, c) for r, c in zip(rows[::2], cols[::2])]
    vec = public / f"vectors/{case}-scenario-route.geojson"
    vec.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"kind": "route"}, "geometry": {"type": "LineString", "coordinates": line}}]}), encoding="utf-8")
    ext = public / f"vectors/{case}-scenario-extent.geojson"
    ext.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"kind": "extent", "breachM": 20}, "geometry": {"type": "Polygon", "coordinates": extent}}] if extent else []}), encoding="utf-8")
    profile = [[round(float(km[i]), 2), round(float(z[rows[i], cols[i]]))] for i in range(0, len(rows), 4)]
    marks = [{"km": round(float(km[i]), 1), "lngLat": lng_lat(rows[i], cols[i])} for i in range(0, len(rows), max(1, len(rows) // 12))]
    return {"routeKm": round(float(km[-1]), 1), "routeEnd": lng_lat(rows[-1], cols[-1]), "lakeAreaKm2": area_km2, "areaRangeKm2": [a_lo, area_km2, a_hi],
            "profile": profile, "marks": marks, "gammaNm3": GAMMA, "slopeFloor": SLOPE_FLOOR, "speedFloorMs": SPEED_FLOOR, "kinematicFactor": round(KINEMATIC, 4),
            "scenarios": scenarios, "routeVector": vec.relative_to(public.parent).as_posix(), "extentVector": ext.relative_to(public.parent).as_posix(),
            "formulas": {k: n for k, (n, _) in FORMULAS.items()}, "roughness": list(N_RANGE), "sectionEveryM": SECTION_EVERY_M,
            "bounds": [round(float(v), 4) for v in (t.c, t.f + t.e * z.shape[0], t.c + t.a * z.shape[1], t.f)], "_shade": str(shade_tif) if shade_tif else None}
