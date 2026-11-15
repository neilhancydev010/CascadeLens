"""Terrain landslide screening and road-corridor exposure, on the Radar Observability grid.

Model A only: where the *terrain* makes slope failure comparatively more likely. It is a transparent rule-based
screen, not a trained model and not a forecast. There is no landslide inventory beyond one event here, so a
machine-learning susceptibility model would only memorise that event. Dynamic triggering (rainfall, soil moisture)
is a separate model that needs data not yet downloaded, see LIMITS.

Every pixel keeps its factor bits, so the class can always be explained:

    STEEP_1  (1)   slope 15 to 25 deg
    STEEP_2  (2)   slope 25 to 35 deg
    STEEP_3  (4)   slope 35 deg or more
    HOLLOW   (8)   convergent ground (negative plan curvature): water and debris collect there
    WET     (16)   topographic wetness index in the top quarter of slopes over 15 deg
"""
from __future__ import annotations

import numpy as np
from rasterio.warp import Resampling, reproject

STEEP_1, STEEP_2, STEEP_3, HOLLOW, WET = 1, 2, 4, 8, 16
SLOPE_BANDS = (15.0, 25.0, 35.0)
CLASSES = [  # (code, label, colour, meaning)
    (1, "Low", "#3B5A55", "Gentle ground (under 15 deg), or moderate slopes with no other factor."),
    (2, "Moderate", "#C9B458", "Moderately steep, or steep but neither convergent nor wet."),
    (3, "High", "#E8873A", "Steep and either convergent or wet."),
    (4, "Very high", "#D9483B", "35 deg or steeper, convergent and wet: where shallow slides and debris flows typically start."),
]
THRESHOLDS = {
    "slopeBandsDeg": {"value": list(SLOPE_BANDS), "provenance": "Project choice of common slope classes; they are not calibrated for Nepal. Each band's share of the mapped 2026 detachment zone is reported so the choice can be checked."},
    "hollow": {"value": "plan curvature < 0 after 3x3 smoothing", "provenance": "Standard terrain-analysis convention (convergent flow)."},
    "wet": {"value": "TWI above the 75th percentile of slopes over 15 deg", "provenance": "Relative, project choice. TWI = ln(a / tan b) with D8 flow accumulation (Beven and Kirkby 1979)."},
}
LIMITS = [
    "Terrain only. Geology, soil, land cover, rainfall and earthquakes are not included, so this is a screen of where terrain favours failure, not a susceptibility map in the full sense.",
    "Not trained or calibrated: no Nepal landslide inventory is loaded. The only check is a one-event consistency check against the UNOSAT 2026 detachment zone. It is not a validation: every unmapped pixel counts as a negative, and neighbouring pixels are not independent.",
    "Not a forecast and not a warning. A high class does not mean a slope is about to fail.",
    "Copernicus DEM GLO-30 resampled to 40 m; flow paths ignore pits and flats, and small gullies are smoothed.",
]


def steep_share(classes: np.ndarray) -> float | None:
    """Percent of cells in class High or Very high, over cells with a valid elevation only. Class 0 (no valid elevation)
    is not assessed, so it counts neither as steep nor as gentle. None when no cell could be assessed."""
    c = np.asarray(classes)
    ok = c > 0
    return round(100 * float((c[ok] >= 3).mean()), 1) if ok.any() else None


def to_grid(src_path, transform, crs, shape) -> np.ndarray:
    import rasterio
    out = np.full(shape, np.nan, np.float32)
    with rasterio.open(src_path) as s:
        reproject(rasterio.band(s, 1), out, dst_transform=transform, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
    return out


def slope_deg(z: np.ndarray, posting: float) -> np.ndarray:
    gy, gx = np.gradient(z, posting)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def plan_curvature(z: np.ndarray, posting: float) -> np.ndarray:
    """Negative = convergent. Plan curvature from second derivatives (Zevenbergen and Thorne form)."""
    from scipy.ndimage import uniform_filter
    zs = uniform_filter(np.nan_to_num(z, nan=np.nanmean(z)), 3)
    zy, zx = np.gradient(zs, posting)
    zyy, zyx = np.gradient(zy, posting)
    zxy, zxx = np.gradient(zx, posting)
    p = zx ** 2 + zy ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        k = -(zxx * zy ** 2 - 2 * zxy * zx * zy + zyy * zx ** 2) / (p ** 1.5)
    k[p < 1e-6] = 0
    return k


def flow_accumulation(z: np.ndarray) -> np.ndarray:
    """D8 upslope cell count (each cell counts itself). Cells drain to their steepest lower neighbour."""
    h, w = z.shape
    zf = np.where(np.isfinite(z), z, np.inf).astype(np.float64)
    pad = np.pad(zf, 1, constant_values=np.inf)
    best = np.zeros((h, w))
    target = np.full((h, w), -1, np.int64)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            nb = pad[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
            drop = (zf - nb) / (np.hypot(dy, dx))
            better = np.isfinite(drop) & (drop > best)
            best[better] = drop[better]
            ys, xs = np.clip(np.arange(h)[:, None] + dy, 0, h - 1), np.clip(np.arange(w)[None, :] + dx, 0, w - 1)
            target[better] = np.broadcast_to(ys * w + xs, (h, w))[better]
    acc = np.ones(h * w)
    order = np.argsort(-zf.ravel(), kind="stable")
    t = target.ravel()
    order = order[np.isfinite(zf.ravel()[order])]
    tl = t[order].tolist()
    a = acc.tolist()
    for i, j in zip(order.tolist(), tl):
        if j >= 0:
            a[j] += a[i]
    return np.array(a).reshape(h, w)


def screen(z: np.ndarray, posting: float) -> dict:
    s = slope_deg(z, posting)
    k = plan_curvature(z, posting)
    acc = flow_accumulation(z)
    with np.errstate(divide="ignore", invalid="ignore"):
        twi = np.log(acc * posting / np.tan(np.radians(np.maximum(s, 0.5))))
    valid = np.isfinite(z) & np.isfinite(s)
    hilly = valid & (s >= SLOPE_BANDS[0])
    wet_cut = float(np.nanpercentile(twi[hilly], 75)) if hilly.any() else np.inf
    f = np.zeros(z.shape, np.uint8)
    f[(s >= SLOPE_BANDS[0]) & (s < SLOPE_BANDS[1])] |= STEEP_1
    f[(s >= SLOPE_BANDS[1]) & (s < SLOPE_BANDS[2])] |= STEEP_2
    f[s >= SLOPE_BANDS[2]] |= STEEP_3
    f[k < 0] |= HOLLOW
    f[hilly & (twi > wet_cut)] |= WET
    f[~valid] = 255
    return {"flags": f, "slope": s, "twi": twi, "wetCut": wet_cut}


def classify(flags: np.ndarray) -> np.ndarray:
    steep = (flags & (STEEP_2 | STEEP_3)) > 0
    very = (flags & STEEP_3) > 0
    extra = ((flags & HOLLOW) > 0).astype(int) + ((flags & WET) > 0).astype(int)
    c = np.ones(flags.shape, np.uint8)
    c[((flags & STEEP_1) > 0) & (extra > 0)] = 2
    c[steep & (extra == 0)] = 2
    c[steep & (extra >= 1)] = 3
    c[very & (extra == 2)] = 4
    c[flags == 255] = 0
    return c


def auc(score: np.ndarray, positive: np.ndarray, negative: np.ndarray) -> float | None:
    """Probability a random positive pixel scores above a random negative one (ties count half)."""
    p, n = score[positive], score[negative]
    if not len(p) or not len(n):
        return None
    vals = np.union1d(p, n)
    cp = np.array([(p == v).sum() for v in vals], float)
    cn = np.array([(n == v).sum() for v in vals], float)
    below = np.cumsum(cn) - cn
    return float(((cp * (below + cn / 2)).sum()) / (len(p) * len(n)))
