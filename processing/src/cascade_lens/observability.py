"""Radar Observability: where can NISAR be trusted, for which task, and why not elsewhere.

Every cell of a 40 m analysis grid gets reason flags (uint16), never one blended score:

    OUTSIDE        (1)  outside the frame's boundingPolygon: not assessed here (a neighbouring frame may cover it)
    NODATA         (2)  inside the frame, but the event product holds no value (non-finite, or mask fill 255)
    LAYOVER        (4)  terrain faces the radar more steeply than the incidence angle
    SHADOW         (8)  terrain faces away more steeply than 90 deg minus the incidence angle (active shadow)
    LOWCOH        (16)  event-pair coherence below COH_MIN
    NOCC          (32)  no reliably unwrapped phase: component label 0 or fill, non-finite phase, or phase exactly 0 (zero-fill)
    LOWBASE       (64)  pre-event (baseline) coherence below COH_MIN
    MASKED       (128)  the event product's own mask flags the pixel: water, or an invalid subswath
    GEOM_UNKNOWN (256)  layover and shadow could not be assessed: DEM, incidence or line of sight missing or invalid
    BASE_NODATA  (512)  the baseline product holds no valid value (non-finite, mask fill, water, invalid subswath or image anomaly)

Classes are then decided per task, because what spoils one task does not spoil another:

    disturbance  "Did the surface change between these dates?"  Low event coherence is the signal here, so it does not count
                 against the cell. A drop can only be seen where the ground was coherent before, so a valid, coherent
                 baseline pair is required. Without a baseline pair this task is not assessed at all.
    movement     "Could ground movement be measured here?"  Needs coherent phase in a reliably unwrapped component.

Missing or invalid inputs never become "Usable": they get their own reason and a "No valid data" or "Not assessed" class.

One coherence product for every flag: unwrappedInterferogram/{pol}/coherenceMagnitude, the dataset that shares a grid with the
unwrapped phase, the connected components and the product mask, and the same dataset the app shows as "Coherence magnitude".
Its 80 m pixels are sampled nearest-neighbour onto the 40 m grid, so each product pixel covers 2 x 2 analysis cells. The 40 m
grid exists for the terrain geometry, which comes from the Copernicus DEM and the product's own radarGrid cubes.
Only active layover and shadow are computed; shadow cast by distant ridges (passive shadow) is not, see LIMITS.
"""
from __future__ import annotations

import json
import pathlib
import re

import h5py
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from shapely import wkt
from shapely.geometry import mapping
from shapely.ops import transform as stransform

from . import nisar, quality

METHOD_VERSION = 2  # 2: product masks applied, missing geometry is "Not assessed", one coherence product. Version 1 ignored masks.
GRID = "/science/LSAR/GUNW/grids/frequencyA"
UNW = f"{GRID}/unwrappedInterferogram"
RADAR = "/science/LSAR/GUNW/metadata/radarGrid"
FLAG_DTYPE = np.uint16
FLAG_NODATA = 65535  # raster nodata; no reachable flag combination equals it (OUTSIDE is only ever set alone)

OUTSIDE, NODATA, LAYOVER, SHADOW, LOWCOH, NOCC, LOWBASE, MASKED, GEOM_UNKNOWN, BASE_NODATA = 1, 2, 4, 8, 16, 32, 64, 128, 256, 512
COH_MIN = 0.3
COH_SENSITIVITY = (0.2, 0.3, 0.4)
MIN_HORIZONTAL_LOS = 1e-3  # a line of sight this close to vertical has no usable look direction
THRESHOLDS = {
    "coherenceMin": {"value": COH_MIN, "provenance": "Project choice. 0.3 is a common lower bound for usable L-band phase; results at 0.2 and 0.4 are reported alongside so the choice can be checked."},
    "layover": {"value": "range slope toward the radar > incidence angle", "provenance": "Standard SAR geometry (layover occurs when the terrain slope facing the sensor exceeds the incidence angle)."},
    "shadow": {"value": "range slope away from the radar > 90 deg - incidence angle", "provenance": "Standard SAR geometry (active radar shadow)."},
    "coherenceProduct": {"value": "unwrappedInterferogram coherenceMagnitude, 80 m, sampled nearest onto the 40 m grid", "provenance": "The coherence that belongs to the unwrapped phase and shares its mask; the same layer the app shows."},
}
LIMITS = [
    "Only active layover and shadow from the local slope. Passive shadow cast by a distant ridge is not modelled, so some shadowed valleys may be marked visible.",
    "The DEM is Copernicus GLO-30 resampled to the analysis grid; small features below the grid size are smoothed.",
    "Coherence comes from the 80 m product, so features narrower than about 80 m are mixed with their surroundings.",
    "Coherence also falls for reasons that are not surface change (wet snow, vegetation, a long time gap). The disturbance task only says whether a change could be seen, not whether one happened.",
    "An exact zero in unwrapped phase is treated as unwrapping fill. A component's own reference pixel can be exactly zero, so at most one real pixel per component may be lost.",
    "Products are Provisional.",
]

# task -> ordered classes: (code, label, colour, meaning). Codes are stable: the frontend and reports index by them.
CLASSES = {
    "disturbance": [
        (1, "Usable", "#5FE0C9", "The radar saw this ground clearly before and across the event, so a change here would show."),
        (2, "Seen, but not reliable", "#F2C46B", "The ground was already incoherent in the baseline pair, so a drop across the event cannot be told apart from normal noise."),
        (3, "Hidden by terrain", "#B07CFF", "Layover or radar shadow: the slope's geometry hides it from this viewing angle."),
        (4, "No valid data in the product", "#6B7682", "Inside the frame, but the product holds no value here, or its own mask flags it (water, an invalid subswath or an image anomaly)."),
        (5, "Outside the frame checked", "#2A3138", "Outside the radar frame assessed here. A neighbouring frame or another track may cover it, but it is not checked yet: no conclusion, not no change."),
        (6, "Not assessed", "#A39B8B", "An input needed for this check is missing or invalid here (terrain geometry, or the baseline pair). No conclusion."),
    ],
    "movement": [
        (1, "Usable", "#5FE0C9", "Phase is coherent and reliably unwrapped, so ground movement could be measured here. Nothing has been measured yet."),
        (2, "Seen, but not reliable", "#F2C46B", "Phase is too noisy (low coherence) or was not reliably unwrapped here, so no movement value can be trusted."),
        (3, "Hidden by terrain", "#B07CFF", "Layover or radar shadow: the slope's geometry hides it from this viewing angle."),
        (4, "No valid data in the product", "#6B7682", "Inside the frame, but the product holds no value here, or its own mask flags it (water, an invalid subswath or an image anomaly)."),
        (5, "Outside the frame checked", "#2A3138", "Outside the radar frame assessed here. A neighbouring frame or another track may cover it, but it is not checked yet: no conclusion, not no movement."),
        (6, "Not assessed", "#A39B8B", "The terrain geometry needed for this check is missing or invalid here. No conclusion."),
    ],
}


def dates(name: str) -> tuple[str, str]:
    d = re.findall(r"_(\d{8})T\d{6}_\d{8}T\d{6}", name)
    iso = lambda s: f"{s[:4]}-{s[4:6]}-{s[6:]}"  # noqa: E731
    return iso(d[0]), iso(d[1])


def geometry_flags(dem: np.ndarray, posting: float, los_e: np.ndarray, los_n: np.ndarray, incidence_deg: np.ndarray) -> np.ndarray:
    """Layover and shadow from the local slope measured along the radar's horizontal look direction.

    los_e, los_n: east and north components of the unit vector from the ground to the sensor. incidence_deg: degrees.
    dem rows run north to south (row 0 is the northern edge). Cells whose slope, incidence or look direction cannot be
    established get GEOM_UNKNOWN instead of a clean bill of health."""
    dzdy_south, dzdx = np.gradient(np.asarray(dem, np.float64), posting)
    dzdn = -dzdy_south
    los_e, los_n, inc = (np.asarray(a, np.float64) for a in (los_e, los_n, incidence_deg))
    h = np.hypot(los_e, los_n)
    with np.errstate(invalid="ignore", divide="ignore"):
        ue, un = los_e / h, los_n / h
        slope = np.degrees(np.arctan(dzdx * ue + dzdn * un))
    # A central difference skips the cell itself, so a missing height is tested directly as well as through its neighbours' slopes
    unknown = ~np.isfinite(np.asarray(dem, np.float64)) | ~np.isfinite(slope) | ~np.isfinite(inc) | (inc <= 0) | (inc >= 90) | ~(h >= MIN_HORIZONTAL_LOS)
    flags = np.zeros(np.shape(dem), FLAG_DTYPE)
    with np.errstate(invalid="ignore"):
        flags[~unknown & (slope > inc)] |= LAYOVER
        flags[~unknown & (-slope > 90 - inc)] |= SHADOW
    flags[unknown] = GEOM_UNKNOWN
    return flags


def classify(flags: np.ndarray, task: str, baseline_assessed: bool = True) -> np.ndarray:
    """Reason flags -> class code for one task (see CLASSES). Later rules win: outside > no valid data > hidden > not assessed > poor."""
    if task not in CLASSES:
        raise ValueError(f"unknown task {task!r}")
    if task == "disturbance" and not baseline_assessed:
        raise ValueError("Disturbance cannot be assessed without a pre-event baseline pair.")
    flags = np.asarray(flags)
    if flags.dtype.kind == "f" and not np.isfinite(flags).all():
        raise ValueError("reason flags must be finite integers")
    flags = flags.astype(np.int64)  # also accepts 8-bit flag rasters written before METHOD_VERSION 2
    disturbance = task == "disturbance"
    out = np.ones(flags.shape, np.uint8)
    out[(flags & (LOWBASE if disturbance else (LOWCOH | NOCC))) > 0] = 2
    out[(flags & (GEOM_UNKNOWN | (BASE_NODATA if disturbance else 0))) > 0] = 6
    out[(flags & (LAYOVER | SHADOW)) > 0] = 3
    out[(flags & (NODATA | MASKED)) > 0] = 4
    out[(flags & OUTSIDE) > 0] = 5
    return out


def summary(classes: np.ndarray, mask: np.ndarray, task: str) -> dict:
    n = int(mask.sum())
    if not n:
        return {"pixels": 0}
    pct = {lbl: round(100 * float((classes[mask] == code).mean()), 1) for code, lbl, *_ in CLASSES[task]}
    usable = pct["Usable"]
    verdict = "Enough evidence" if usable >= 50 else "Partial evidence" if usable >= 20 else "Insufficient evidence"
    return {"pixels": n, "percent": pct, "verdict": verdict, "verdictRule": "Usable share: 50% or more = enough, 20 to 50% = partial, under 20% = insufficient."}


def compare_usable(classes_this: np.ndarray, classes_other: np.ndarray, mask: np.ndarray) -> dict:
    """Share of a zone usable from this viewing direction only, the other only, both, either, or neither (same grid, same task).

    Only class 1 counts as usable. Everything else, including outside the frame and not assessed, counts as not usable, so
    'only this view' is ground the other view could not judge. The views are compared, never merged into one reason."""
    if classes_this.shape != classes_other.shape:
        raise ValueError("views are not on one analysis grid")
    n = int(mask.sum())
    if not n:
        return {"pixels": 0}
    a, b = (classes_this == 1) & mask, (classes_other == 1) & mask
    pct = lambda x: round(100 * float(x.sum()) / n, 1)  # noqa: E731
    return {"pixels": n, "onlyThis": pct(a & ~b), "onlyOther": pct(b & ~a), "both": pct(a & b), "either": pct(a | b), "neither": pct(mask & ~(a | b))}


def _on_grid(h5, ds_path: str, gxc: np.ndarray, gyc: np.ndarray) -> tuple[np.ndarray, nisar.Grid]:
    """Nearest product pixel for every analysis-cell centre, as float64 (exact for the uint8/uint16 masks and labels).
    Cells beyond the product grid are NaN."""
    grid = nisar.find_grid(h5, ds_path)
    ci = np.rint((gxc - grid.x[0]) / grid.dx).astype(np.int64)
    ri = np.rint((gyc - grid.y[0]) / grid.dy).astype(np.int64)
    okc, okr = (ci >= 0) & (ci < grid.x.size), (ri >= 0) & (ri < grid.y.size)
    out = np.full((gyc.size, gxc.size), np.nan)
    if okc.any() and okr.any():
        c0, c1, r0, r1 = ci[okc].min(), ci[okc].max(), ri[okr].min(), ri[okr].max()
        block = h5[ds_path][r0:r1 + 1, c0:c1 + 1].astype(np.float64)
        out[np.ix_(okr, okc)] = block[np.ix_(ri[okr] - r0, ci[okc] - c0)]
    return out, grid


def _pair_layers(path: pathlib.Path, pol: str, gxc: np.ndarray, gyc: np.ndarray, epsg: int | None) -> dict:
    """Coherence, components, phase and mask of one GUNW pair on the analysis grid, all from the unwrapped grid."""
    paths = {"coh": f"{UNW}/{pol}/coherenceMagnitude", "cc": f"{UNW}/{pol}/connectedComponents", "phase": f"{UNW}/{pol}/unwrappedPhase", "mask": f"{UNW}/mask"}
    with h5py.File(path, "r") as h:
        missing = [p for p in paths.values() if p not in h]
        if missing:
            raise ValueError(f"{path.name}: missing {missing}; without the product mask its validity cannot be checked")
        out, grids = {}, {}
        for k, p in paths.items():
            out[k], grids[k] = _on_grid(h, p, gxc, gyc)
        if any(not grids["coh"].same_as(g) for g in grids.values()):
            raise ValueError(f"{path.name}: coherence, phase, components and mask are not on one grid")
        if epsg is not None and grids["coh"].epsg != epsg:
            raise ValueError(f"{path.name}: EPSG {grids['coh'].epsg}, expected {epsg}")
        out["ccFill"] = nisar.fill_value(h[paths["cc"]], quality.GUNW_CC_FILL_SPEC)
        out["track"] = int(np.asarray(h["/science/LSAR/identification/trackNumber"][()]).item())
        out["frame"] = int(np.asarray(h["/science/LSAR/identification/frameNumber"][()]).item())
    with np.errstate(invalid="ignore"):
        out["coh"][~(out["coh"] > 0)] = np.nan  # coherence of 0 or below is not an estimate here: no value
    m = np.where(np.isfinite(out["mask"]), out["mask"], 255).astype(np.int64)  # all 32 bits: anomaly flags sit above bit 8
    d = quality.decode_gunw_mask(m)
    out["maskFill"], out["maskInvalid"] = d["fill"], d["unusable"]
    out["datasets"] = paths
    return out


def combine_frames(primary: np.ndarray, other: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Flags for two neighbouring frames of the same pair on one analysis grid. A cell keeps the primary frame's flags
    wherever that frame covers it; a cell outside the primary frame takes the other frame's flags when that frame covers it.
    Returns the combined flags and the cells taken from the other frame. Where both cover a cell, the primary frame wins,
    so a reason is never mixed from two products."""
    if primary.shape != other.shape:
        raise ValueError("frames are not on one analysis grid")
    take = ((primary & OUTSIDE) != 0) & ((other & OUTSIDE) == 0) & (other != FLAG_NODATA) & (primary != FLAG_NODATA)
    return np.where(take, other, primary), take


def assess(gunw: pathlib.Path, baseline: pathlib.Path | None, dem_path: pathlib.Path, bounds_lonlat, posting: float = 40.0, pol: str = "HH") -> dict:
    """Run the assessment on one GUNW pair over a lon/lat box. Returns arrays and metadata (no files written)."""
    with h5py.File(gunw, "r") as h:
        epsg = nisar.find_grid(h, f"{UNW}/{pol}/coherenceMagnitude").epsg
        footprint = wkt.loads(h["/science/LSAR/identification/boundingPolygon"][()].decode())
        meta = {k: h[f"/science/LSAR/identification/{k}"][()] for k in ("trackNumber", "frameNumber", "orbitPassDirection", "lookDirection", "granuleId", "compositeReleaseId", "productVersion")}
    meta = {k: (v.decode() if isinstance(v, bytes) else int(v)) for k, v in meta.items()}
    to_utm = Transformer.from_crs(4326, epsg, always_xy=True).transform
    w, s, e, n = bounds_lonlat
    xs, ys = to_utm([w, e, w, e], [s, s, n, n])
    gx0, gx1 = np.floor(min(xs) / posting) * posting, np.ceil(max(xs) / posting) * posting
    gy0, gy1 = np.floor(min(ys) / posting) * posting, np.ceil(max(ys) / posting) * posting
    cols, rows = int((gx1 - gx0) / posting), int((gy1 - gy0) / posting)
    transform = from_origin(gx0, gy1, posting, posting)
    gxc = gx0 + (np.arange(cols) + 0.5) * posting
    gyc = gy1 - (np.arange(rows) + 0.5) * posting

    ev = _pair_layers(gunw, pol, gxc, gyc, epsg)
    base = _pair_layers(baseline, pol, gxc, gyc, epsg) if baseline else None
    if base is not None and (base["track"], base["frame"]) != (ev["track"], ev["frame"]):
        raise ValueError(f"Baseline is track {base['track']} frame {base['frame']}, event pair is track {ev['track']} frame {ev['frame']}: not comparable")

    dem = np.full((rows, cols), np.nan, np.float32)
    with rasterio.open(dem_path) as d:
        reproject(rasterio.band(d, 1), dem, dst_transform=transform, dst_crs=f"EPSG:{epsg}", dst_nodata=np.nan, resampling=Resampling.bilinear)

    with h5py.File(gunw, "r") as h:
        r = h[RADAR]
        rx, ry, hz = r["xCoordinates"][()], r["yCoordinates"][()], r["heightAboveEllipsoid"][()]
        # One height layer of the cubes for the whole box, the one nearest the median terrain height (a documented simplification)
        k = int(np.argmin(np.abs(hz - np.nanmedian(dem)))) if np.isfinite(dem).any() else 0
        lx, ly, inc = r["losUnitVectorX"][k], r["losUnitVectorY"][k], r["incidenceAngle"][k]
    xi = np.clip(np.searchsorted(rx, gxc), 0, rx.size - 1)
    yi = np.clip(np.searchsorted(-ry, -gyc), 0, ry.size - 1)
    los_e, los_n, incd = (a[np.ix_(yi, xi)].astype(np.float64) for a in (lx, ly, inc))

    flags = geometry_flags(dem, posting, los_e, los_n, incd)
    fp = rasterize([mapping(stransform(to_utm, footprint))], out_shape=(rows, cols), transform=transform).astype(bool)
    inside = fp
    coh = ev["coh"]
    flags[inside & (~np.isfinite(coh) | ev["maskFill"])] |= NODATA
    flags[inside & ev["maskInvalid"] & ~ev["maskFill"]] |= MASKED
    with np.errstate(invalid="ignore"):
        flags[inside & np.isfinite(coh) & (coh < COH_MIN)] |= LOWCOH
    no_phase = quality.unreliable_component(ev["cc"], ev["ccFill"]) | ~np.isfinite(ev["phase"]) | quality.zero_filled_phase(ev["phase"])
    flags[inside & no_phase] |= NOCC
    bcoh = None
    if base is not None:
        bcoh = base["coh"]
        b_bad = ~np.isfinite(bcoh) | base["maskFill"] | base["maskInvalid"]
        flags[inside & b_bad] |= BASE_NODATA
        with np.errstate(invalid="ignore"):
            flags[inside & ~b_bad & (bcoh < COH_MIN)] |= LOWBASE
    flags[~fp] = OUTSIDE
    if (flags == FLAG_NODATA).any():
        raise AssertionError("a flag combination collided with the raster nodata value")

    sens = {}
    for t in COH_SENSITIVITY:
        f = flags & FLAG_DTYPE(~LOWCOH & 0xFFFF)
        with np.errstate(invalid="ignore"):
            f[inside & np.isfinite(coh) & (coh < t)] |= LOWCOH
        sens[str(t)] = round(100 * float((classify(f, "movement")[inside] == 1).mean()), 1) if inside.any() else None

    inc_ok = incd[np.isfinite(incd)]
    return {"flags": flags, "coherence": coh, "baseline": bcoh, "dem": dem, "transform": transform, "epsg": epsg, "meta": meta,
            "pair": dates(gunw.name), "baselinePair": dates(baseline.name) if baseline else None, "methodVersion": METHOD_VERSION,
            "losEast": float(np.nanmedian(los_e)), "losNorth": float(np.nanmedian(los_n)),
            "incidenceDeg": [round(float(np.percentile(inc_ok, 5)), 1), round(float(np.percentile(inc_ok, 95)), 1)] if inc_ok.size else None,
            "geometryHeightM": float(hz[k]), "ccFillValue": ev["ccFill"], "datasets": ev["datasets"],
            "sensitivity": {"movementUsablePct": sens, "denominator": "All analysis cells inside the frame footprint, over the whole case area.",
                            "rule": "The same rule as the movement class, with only the coherence threshold changed."},
            "geometryNotAssessedPct": round(100 * float(((flags & GEOM_UNKNOWN) > 0)[inside].mean()), 2) if inside.any() else None}


def zone_mask(geom_lonlat, epsg: int, transform, shape) -> np.ndarray:
    to_utm = Transformer.from_crs(4326, epsg, always_xy=True).transform
    return rasterize([mapping(stransform(to_utm, geom_lonlat))], out_shape=shape, transform=transform).astype(bool)


def to_json(obj) -> str:
    return json.dumps(obj, indent=1)
