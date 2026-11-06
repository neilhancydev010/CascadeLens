"""Glacial lake case: one NISAR GCOV track over a lake, several dates, lake size measured on each date.

Every date is put on one shared 20 m UTM grid: quad-pol files are already 20 m, dual-pol 10 m files are averaged 2x2 in power.
Calm open water reflects L-band radar away from the satellite, so a lake is darker than the rock and ice around it.
The lake is the dark area (HH + HV after 3x3 smoothing below a threshold) that overlaps the lake's known position.
The area range comes from rerunning with a threshold 1 dB brighter and 1 dB darker: it is a method range, not a formal error.
"""
from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime, timezone

import h5py
import numpy as np
from PIL import Image
from pyproj import Transformer
from rasterio import features
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds, transform_geom
from scipy import ndimage

from . import export, motion, nisar, quality

POSTING = 20.0
FILTER = 3
THRESHOLD_DB = -7.0
THRESHOLD_RANGE = (-6.0, -8.0)
ATTRIBUTION = "NASA/JPL-Caltech/ISRO, NISAR; distributed by ASF DAAC"
GREY = export.COLORMAPS["grey"]


def _date(path: pathlib.Path) -> str:
    m = re.search(r"_(\d{8})T\d{6}_\d{8}T", path.name)
    if not m:
        raise ValueError(f"No acquisition date in {path.name}")
    d = m.group(1)
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def read_clip(path: pathlib.Path, x0: float, y0: float, rows: int, cols: int) -> dict:
    """HH and HV power and validity on the shared 20 m grid whose top-left pixel centre is (x0, y0)."""
    root = nisar.ROOT["GCOV"]
    with h5py.File(path, "r") as h:
        g = h[root]
        x, y = g["xCoordinates"][()], g["yCoordinates"][()]
        step = float(x[1] - x[0])
        k = int(round(POSTING / step))
        if k not in (1, 2):
            raise ValueError(f"{path.name}: posting {step} m is not 10 or 20 m")
        half = (k - 1) * step / 2  # a 2x2 block of 10 m pixels is centred half a 10 m pixel from its first pixel
        c0 = int(np.argmin(np.abs(x - (x0 - half))))
        r0 = int(np.argmin(np.abs(y - (y0 + half))))
        if abs(x[c0] - (x0 - half)) > 0.5 or abs(y[r0] - (y0 + half)) > 0.5:
            raise ValueError(f"{path.name}: grid does not line up with the shared grid")
        win = np.s_[r0:r0 + rows * k, c0:c0 + cols * k]
        terms = [t.decode() for t in g["listOfCovarianceTerms"][()]]
        flag = nisar.flag(h, nisar.GCOV_MASKING_FLAG)
        ident = nisar.identify(h)
        out = {"terms": terms, "posting": step, "identification": ident, "epsg": int(g["projection"][()])}
        for term in ("HHHH", "HVHV"):
            a = quality.clean(g[term][win])
            if a.shape != (rows * k, cols * k):
                raise ValueError(f"{path.name}: lake box runs off the edge of the frame")
            if k == 2:
                with np.errstate(invalid="ignore"):
                    a = np.nanmean(a.reshape(rows, 2, cols, 2), axis=(1, 3)) if np.isnan(a).any() else a.reshape(rows, 2, cols, 2).mean(axis=(1, 3))
            out[term] = a.astype(np.float32)
        mask = g["mask"][win][::k, ::k]
        out["validity"] = quality.gcov_validity(out["HHHH"], mask, flag)
        out["validity"][~np.isfinite(out["HVHV"])] = quality.NODATA
    return out


def _smooth(a: np.ndarray) -> np.ndarray:
    filled = np.where(np.isfinite(a), a, np.nanmedian(a))
    return ndimage.uniform_filter(filled, FILTER)


def detect_lake(hh: np.ndarray, hv: np.ndarray, seed: np.ndarray, threshold: float) -> np.ndarray:
    """Dark area overlapping the seed disk. Opening removes thin dark strips such as radar shadow edges."""
    total = 10 * np.log10(np.clip(_smooth(hh) + _smooth(hv), 1e-10, None))
    dark = ndimage.binary_opening(total < threshold, iterations=2)
    lab, _ = ndimage.label(dark)
    ids = np.unique(lab[seed & (lab > 0)])
    if not ids.size:
        return np.zeros_like(dark)
    biggest = max(ids, key=lambda i: int((lab == i).sum()))
    return ndimage.binary_fill_holes(lab == biggest)


def _channels(hh: np.ndarray, hv: np.ndarray) -> list[np.ndarray]:
    hh_db, hv_db = 10 * np.log10(np.clip(_smooth(hh), 1e-10, None)), 10 * np.log10(np.clip(_smooth(hv), 1e-10, None))
    return [hh_db, hv_db, hh_db - hv_db]


def rgb_limits(hh: np.ndarray, hv: np.ndarray) -> list[tuple[float, float]]:
    """2nd to 98th percentile of each channel on the first date, then kept fixed so every date uses the same colours."""
    return [tuple(float(x) for x in np.nanpercentile(c, [2, 98])) for c in _channels(hh, hv)]


def _rgb(hh: np.ndarray, hv: np.ndarray, limits) -> np.ndarray:
    """Colour radar: red = HH, green = HV, blue = HH/HV. Water dark, rough rock bright, debris and vegetation greener."""
    rgb = np.dstack([np.clip((c - lo) / (hi - lo), 0, 1) for c, (lo, hi) in zip(_channels(hh, hv), limits)])
    return (rgb * 255).astype(np.uint8)


TERRAIN_STEP = 2  # 3D model grid: every 2nd pixel of the 20 m clip, so 40 m between points


def prepare_terrain(dem, transform, epsg, rows, cols, series, pictures, greys, lakes, out, rel) -> dict:
    """Heights on the same grid as the radar clip, for the 3D block model, plus full-clip drape images for every date.

    Copernicus DEM is a surface model from 2011 to 2015: the lake surface in it is the water level of those years."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject
    out.mkdir(parents=True, exist_ok=True)
    h = np.full((rows, cols), np.nan, np.float32)
    with rasterio.open(dem) as src:
        reproject(rasterio.band(src, 1), h, dst_transform=transform, dst_crs=f"EPSG:{epsg}", dst_nodata=np.nan, resampling=Resampling.bilinear)
    if np.isnan(h).mean() > 0.01:
        raise ValueError(f"{pathlib.Path(dem).name} does not cover the lake box ({np.isnan(h).mean():.0%} missing)")
    h = np.where(np.isnan(h), np.nanmin(h), h)
    k = TERRAIN_STEP
    small = h[: rows // k * k, : cols // k * k].reshape(rows // k, k, cols // k, k).mean(axis=(1, 3)).astype(np.float32)
    (out / "heights.bin").write_bytes(small.astype("<f4").tobytes())
    for point, picture, grey, lake in zip(series, pictures, greys, lakes):
        tag = point["date"].replace("-", "")
        Image.fromarray(picture, "RGB").save(out / f"rgb_{tag}.jpg", quality=90)
        Image.fromarray(grey, "L").save(out / f"hh_{tag}.jpg", quality=90)
        point["drape"] = {"rgb": rel(out / f"rgb_{tag}.jpg"), "hh": rel(out / f"hh_{tag}.jpg")}
        point["outlineFull"] = _outline_path(lake)
    level = float(np.median(h[lakes[0]])) if lakes[0].any() else None
    lake_small = lakes[0][: rows // k * k, : cols // k * k].reshape(rows // k, k, cols // k, k).any(axis=(1, 3))
    path = flow_path(small, lake_small)
    return {"heights": rel(out / "heights.bin"), "width": int(small.shape[1]), "height": int(small.shape[0]), "spacingM": POSTING * k,
            "minM": round(float(small.min()), 1), "maxM": round(float(small.max()), 1), "lakeLevelM": round(level, 1) if level else None,
            "drapeSize": [cols, rows], "source": pathlib.Path(dem).name, **path,
            "attribution": "Copernicus DEM GLO-30: © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA",
            "note": "Heights from Copernicus DEM (2011 to 2015 survey), not from NISAR. The radar is draped on top."}


def flow_path(z: np.ndarray, lake: np.ndarray, max_steps: int = 2000) -> dict:
    """Downhill route from the lake's lowest shore cell to the edge of the block, steepest drop first.

    Where the grid has a hollow with no lower neighbour, the route takes the lowest unvisited neighbour and carries on,
    as water would after filling the hollow. An illustration of where water would go, not a hydraulic model."""
    if not lake.any():
        return {}
    rows, cols = z.shape
    shore = ndimage.binary_dilation(lake) & ~lake
    rr, cc = np.where(shore)
    i = int(np.argmin(z[rr, cc]))
    r, c = int(rr[i]), int(cc[i])
    seen = lake.copy()
    route = [(c, r)]
    seen[r, c] = True
    while 0 < r < rows - 1 and 0 < c < cols - 1 and len(route) < max_steps:
        best = None
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = r + dr, c + dc
                if (dr or dc) and not seen[nr, nc]:
                    drop = (z[r, c] - z[nr, nc]) / (1.4142 if dr and dc else 1)
                    if best is None or drop > best[0]:
                        best = (drop, nr, nc)
        if best is None:
            break
        _, r, c = best
        seen[r, c] = True
        route.append((c, r))
    lr, lc = np.where(lake)
    centre = int(np.argmin((lr - lr.mean()) ** 2 + (lc - lc.mean()) ** 2))
    return {"flowPath": [[c, r, round(float(z[r, c]), 1)] for c, r in route], "lakeSeed": [int(lc[centre]), int(lr[centre])],
            "outlet": [route[0][0], route[0][1]]}


def compare_window(lake: np.ndarray, rows: int, cols: int, pad: int) -> tuple[int, int, int, int]:
    """Row and column range around every date's lake, padded and widened to 4:3, kept inside the clip."""
    if not lake.any():
        return 0, rows, 0, cols
    rr, cc = np.where(lake)
    r0, r1, c0, c1 = rr.min() - pad, rr.max() + pad + 1, cc.min() - pad, cc.max() + pad + 1
    h, w = r1 - r0, c1 - c0
    if w < h * 4 / 3:
        grow = int(round(h * 4 / 3 - w)); c0 -= grow // 2; c1 += grow - grow // 2
    else:
        grow = int(round(w * 3 / 4 - h)); r0 -= grow // 2; r1 += grow - grow // 2
    h, w = int(min(r1 - r0, rows)), int(min(c1 - c0, cols))
    r0, c0 = int(np.clip(r0, 0, rows - h)), int(np.clip(c0, 0, cols - w))
    return r0, r0 + h, c0, c0 + w


def _outline_path(lake: np.ndarray) -> str:
    """SVG path of the lake edge in pixel coordinates of the compare images."""
    parts = []
    for geom, v in features.shapes(lake.astype(np.uint8), mask=lake):
        for ring in geom["coordinates"]:
            parts.append("M" + "L".join(f"{x:.0f},{y:.0f}" for x, y in ring) + "Z")
    return "".join(parts)


def prepare(cfg: dict, files: list[pathlib.Path], public: pathlib.Path, work: pathlib.Path, qa_dir: pathlib.Path, dem: pathlib.Path | None = None,
            pair_folders: list[pathlib.Path] | None = None) -> dict:
    case = cfg["id"]
    lon, lat = cfg["lake"]["lng"], cfg["lake"]["lat"]
    rows, cols = cfg["box_rows"], cfg["box_cols"]
    zmin, zmax = cfg["zoom"]
    epsg = cfg["epsg"]
    to_utm = Transformer.from_crs(4326, epsg, always_xy=True)
    cx, cy = to_utm.transform(lon, lat)
    # Shared grid: pixel centres on the 20 m GCOV grid (xCoordinates of the 20 m files end in 0, offset 10 from the 10 m files' 5)
    x0 = np.floor((cx - cols / 2 * POSTING) / POSTING) * POSTING + cfg["grid_offset"]
    y0 = np.floor((cy + rows / 2 * POSTING) / POSTING) * POSTING + cfg["grid_offset"]
    transform = from_origin(x0 - POSTING / 2, y0 + POSTING / 2, POSTING, POSTING)
    bounds = list(transform_bounds(f"EPSG:{epsg}", "EPSG:4326", x0 - POSTING / 2, y0 + POSTING / 2 - rows * POSTING, x0 - POSTING / 2 + cols * POSTING, y0 + POSTING / 2, densify_pts=21))
    yy, xx = np.mgrid[0:rows, 0:cols]
    pc, pr = (cx - x0) / POSTING, (y0 - cy) / POSTING
    seed = (xx - pc) ** 2 + (yy - pr) ** 2 <= (cfg["lake"]["seed_radius_m"] / POSTING) ** 2

    files = sorted(files, key=_date)
    rel = lambda p: pathlib.Path(p).relative_to(public.parent).as_posix()  # noqa: E731
    dates, hh_steps, rgb_steps, granules, qa = [], [], [], [], {"files": [], "method": {}}
    lake_features, hv_stack, series = [], [], []
    limits = None
    lakes, pictures, greys = [], [], []
    for path in files:
        date = _date(path)
        c = read_clip(path, x0, y0, rows, cols)
        if c["epsg"] != epsg:
            raise ValueError(f"{path.name}: EPSG {c['epsg']}, expected {epsg}")
        hh, hv, valid = c["HHHH"], c["HVHV"], c["validity"]
        hv_stack.append(np.where(valid == quality.VALID, hv, np.nan))
        lake = detect_lake(hh, hv, seed, THRESHOLD_DB)
        alt = [detect_lake(hh, hv, seed, t).sum() * POSTING ** 2 / 1e6 for t in THRESHOLD_RANGE]
        area = float(lake.sum() * POSTING ** 2 / 1e6)
        series.append({"date": date, "areaKm2": round(area, 3), "lowKm2": round(float(min(alt)), 3), "highKm2": round(float(max(alt)), 3),
                       "validPct": round(float((valid == quality.VALID).mean() * 100), 1), "polarization": "quad" if len(c["terms"]) > 2 else "dual",
                       "nativePostingM": c["posting"]})
        lakes.append(lake)
        for geom, v in features.shapes(lake.astype(np.uint8), mask=lake, transform=transform):
            lake_features.append({"type": "Feature", "properties": {"date": date, "areaKm2": round(area, 3)}, "geometry": transform_geom(f"EPSG:{epsg}", "EPSG:4326", geom)})
        tag = date.replace("-", "")
        tif = export.write_geotiff(work / f"hh_{tag}.tif", hh, transform, epsg, tags={"SOURCE_FILE": path.name, "SOURCE_DATASET": f"{nisar.ROOT['GCOV']}/HHHH"})
        vtif = export.write_geotiff(work / f"hh_{tag}.validity.tif", valid, transform, epsg, nodata=255)
        cog = export.to_cog(tif, public / f"sampling/{case}/hh_{tag}.tif")
        vcog = export.to_cog(vtif, public / f"sampling/{case}/hh_{tag}_validity.tif")
        db = np.where(valid == quality.VALID, 10 * np.log10(np.clip(hh, 1e-10, None)), np.nan).astype(np.float32)
        dbt = export.write_geotiff(work / f"hhdb_{tag}.tif", db, transform, epsg)
        warped, tx, ty = export.warp_to_tile_grid(dbt, zmax)
        folder = public / f"tiles/{case}/hh/{tag}"
        n = export.write_pyramid(export.colorize(warped, GREY, -22.0, 2.0), tx, ty, zmax, zmin, folder)
        src = {"frame": cfg["frame"], "granule": path.stem, "sourceFilename": path.name, "sourceDataset": f"{nisar.ROOT['GCOV']}/HHHH", "bounds": bounds,
               "sampling": rel(cog), "validity": rel(vcog), "validFraction": float((valid == quality.VALID).mean()), "maskedFraction": float((valid == quality.MASKED).mean()),
               "tiles": {"url": f"{rel(folder)}/{{z}}/{{x}}/{{y}}.png", "minzoom": zmin, "maxzoom": zmax, "count": n}}
        hh_steps.append({"label": date, "sources": [src]})
        limits = limits if dates else rgb_limits(hh, hv)
        rgb = _rgb(hh, hv, limits)
        alpha = np.where(valid == quality.NODATA, 0, 255).astype(np.uint8)
        bands = np.moveaxis(np.dstack([rgb, alpha]), -1, 0)
        rgba, tx, ty = export.warp_rgba(bands, transform, f"EPSG:{epsg}", bounds, zmax)
        folder = public / f"tiles/{case}/rgb/{tag}"
        n = export.write_pyramid(rgba, tx, ty, zmax, zmin, folder, smooth=True)
        rgb_steps.append({"label": date, "sources": [{**{k: v for k, v in src.items() if k not in ("sampling", "validity")}, "sourceDataset": "HHHH, HVHV", "tiles": {"url": f"{rel(folder)}/{{z}}/{{x}}/{{y}}.png", "minzoom": zmin, "maxzoom": zmax, "count": n}}]})
        pictures.append(np.where(alpha[..., None] > 0, rgb, 0).astype(np.uint8))
        greys.append(np.nan_to_num(np.clip((db + 22) / 24, 0, 1) * 255).astype(np.uint8))
        dates.append(date)
        granules.append({"file_id": path.stem, "group": case, "product": "GCOV", "frame": cfg["frame"], "direction": cfg["direction"], "track": cfg["track"], "ref_date": date, "sec_date": None,
                         "size_mb": round(path.stat().st_size / 1e6, 1), "geometry": None, "status": "sampleable"})
        qa["files"].append({"file": path.name, "date": date, "bytes": path.stat().st_size, "terms": c["terms"], "postingM": c["posting"], "identification": c["identification"],
                            "validPct": series[-1]["validPct"], "lakeAreaKm2": area})
        print(f"{date}: lake {area:.3f} km2 ({min(alt):.3f} to {max(alt):.3f}), {c['posting']:.0f} m {series[-1]['polarization']}-pol")

    # Compare images: crop to the lake with some shore around it, 4:3, so the lake fills the swipe view
    crop = compare_window(np.any(np.stack(lakes), axis=0), rows, cols, cfg.get("compare_pad_px", 60))
    r0, r1, c0, c1 = crop
    for point, picture, lk in zip(series, pictures, lakes):
        img = public / f"compare/{case}/{point['date'].replace('-', '')}.jpg"
        img.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(picture[r0:r1, c0:c1], "RGB").save(img, quality=90)
        point["image"] = rel(img)
        point["outline"] = _outline_path(lk[r0:r1, c0:c1])

    terrain = prepare_terrain(dem, transform, epsg, rows, cols, series, pictures, greys, lakes, public / f"terrain/{case}", rel) if dem else None

    # Backdrop: median HV of every date, grey, so the map has context without any other dataset
    backdrop = np.nanmedian(np.stack(hv_stack), axis=0).astype(np.float32)
    bvalid = np.where(np.isfinite(backdrop), quality.VALID, quality.NODATA).astype(np.uint8)
    btif = export.write_geotiff(work / "backdrop.tif", np.where(np.isfinite(backdrop), 10 * np.log10(np.clip(backdrop, 1e-10, None)), np.nan).astype(np.float32), transform, epsg)
    bvt = export.write_geotiff(work / "backdrop.validity.tif", bvalid, transform, epsg, nodata=255)
    bcog, bvcog = export.to_cog(btif, public / f"sampling/{case}/backdrop.tif"), export.to_cog(bvt, public / f"sampling/{case}/backdrop_validity.tif")
    warped, tx, ty = export.warp_to_tile_grid(btif, zmax)
    n = export.write_pyramid(export.colorize(warped, ["#0b0f11", "#7d8a8f"], -30.0, -8.0), tx, ty, zmax, zmin, public / f"tiles/{case}/backdrop")

    vec = public / f"vectors/{case}-lake.geojson"
    vec.parent.mkdir(parents=True, exist_ok=True)
    vec.write_text(json.dumps({"type": "FeatureCollection", "features": lake_features}), encoding="utf-8")

    areas = [s["areaKm2"] for s in series]
    spread = max(s["highKm2"] - s["lowKm2"] for s in series) / 2
    change = areas[-1] - areas[0]
    qa["method"] = {"postingM": POSTING, "filter": FILTER, "thresholdDb": THRESHOLD_DB, "thresholdRange": THRESHOLD_RANGE, "seedRadiusM": cfg["lake"]["seed_radius_m"],
                    "areas": areas, "changeKm2": round(change, 3), "methodHalfRangeKm2": round(spread, 3)}
    qa_dir.mkdir(parents=True, exist_ok=True)
    (qa_dir / f"{case}-report.json").write_text(json.dumps(qa, indent=1), encoding="utf-8")

    maturity = nisar_maturity(qa["files"][0]["identification"])
    gcov_limits = ["Provisional data: calibrated and partly validated, not for final scientific conclusions.",
                   "Dates alternate between dual-pol 10 m and quad-pol 20 m acquisitions. All are shown on a shared 20 m grid.",
                   "Radar shadow behind steep slopes also looks dark. Shadows do not change between dates on this track, so they do not move."]
    common = {"groupId": None, "mission": "NISAR", "instrument": "L-SAR", "productType": "GCOV", "orbitDirection": cfg["direction"], "track": cfg["track"], "frames": [cfg["frame"]],
              "postingM": [POSTING, POSTING], "crs": f"EPSG:{epsg}", "qualityLayerIds": [], "status": "sampleable", "statusReason": None, "productMaturity": maturity,
              "sourceGranules": [p.stem for p in files], "attribution": ATTRIBUTION, "acquisition": {"reference": dates[0], "secondary": dates[-1]}}
    hh_layer = {**common, "id": f"{case}:hh", "name": "Radar brightness (HH)", "category": "gridded", "measurementClass": "measurement", "measurementType": "gcov-backscatter",
                "kind": "continuous", "units": "1", "unitsNote": "Gamma-0 backscatter, linear in the file, shown in dB.", "displayDb": True, "polarization": ["HH"],
                "sources": hh_steps[-1]["sources"], "timeSteps": hh_steps,
                "stats": export.statistics(np.array([-22.0, 2.0]), fixed=(-22.0, 2.0)),
                "legend": {"type": "continuous", "stops": GREY, "min": -22, "max": 2, "unit": "dB", "lowLabel": "Dark: calm water, shadow", "highLabel": "Bright: rough rock, slopes facing the radar"},
                "explanation": {"what": "How much of the radar pulse bounced back to NISAR on each date. HH means sent and received horizontally.",
                                "measures": "Backscatter strength. Calm water acts like a mirror and sends the pulse away, so the lake is dark.",
                                "inspect": "Step through the dates and watch the dark lake shape. Click a point to read the stored value.",
                                "establishes": "Where open water and rough surfaces are on each date. It does not show depth or water level."},
                "limitations": gcov_limits}
    rgb_layer = {**common, "id": f"{case}:rgb", "name": "Colour radar (HH, HV, HH/HV)", "category": "gridded", "measurementClass": "derived", "measurementType": "gcov-composite",
                 "kind": "continuous", "units": None, "status": "renderable", "sources": rgb_steps[-1]["sources"], "timeSteps": rgb_steps,
                 "legend": {"type": "categorical", "stops": ["#000000", "#6b4fd8", "#b8d23a", "#fff6b0"], "labels": None, "unit": None,
                            "keys": [{"color": "#000000", "label": "Black: calm water, or radar shadow"}, {"color": "#6b4fd8", "label": "Purple: smooth bare rock, ice, snow"},
                                     {"color": "#b8d23a", "label": "Yellow-green: rough moraine, boulders, debris"}, {"color": "#fff6b0", "label": "Bright blobs: steep slopes facing the radar (distorted)"}]},
                 "explanation": {"what": "Two radar channels and their ratio mixed into one colour picture.",
                                 "measures": "Red is HH brightness, green is HV (which rises with rough, jumbled surfaces such as debris and vegetation), blue is HH divided by HV.",
                                 "inspect": "The lake is near black. Smooth rock, ice and snow look purple. Rough moraines and debris look yellow-green. Bright blobs are steep slopes squashed by the radar's side view.",
                                 "establishes": "A visual guide only. Colours are not measurements, so the inspector does not sample this layer."},
                 "limitations": gcov_limits + ["Colours are stretched for display. Compare shapes between dates, not exact colours."]}
    backdrop_layer = {**common, "id": "context:terrain", "name": "Radar backdrop (median HV)", "category": "terrain", "measurementClass": "derived", "measurementType": "gcov-backdrop",
                      "kind": "continuous", "units": "dB", "sources": [{"frame": cfg["frame"], "granule": "median of all dates", "sourceFilename": "median of all dates", "bounds": bounds,
                                                                         "sampling": rel(bcog), "validity": rel(bvcog), "tiles": {"url": f"data/tiles/{case}/backdrop/{{z}}/{{x}}/{{y}}.png", "minzoom": zmin, "maxzoom": zmax, "count": n}}],
                      "legend": {"type": "continuous", "stops": ["#0b0f11", "#7d8a8f"], "min": -30, "max": -8, "unit": "dB"},
                      "explanation": {"what": "The median HV radar brightness of all dates, used as a quiet background.", "measures": "HV backscatter in dB.",
                                      "inspect": "Use it to find your way around the valley.", "establishes": "Landscape context only."},
                      "limitations": ["A median of several dates, so it belongs to no single date."]}
    lake_layer = {"id": "ref:lake-edge", "groupId": None, "name": "Lake edge measured from radar", "category": "reference", "mission": "NISAR", "instrument": "L-SAR", "productType": "Derived here",
                  "measurementClass": "derived", "measurementType": "reference", "kind": "vector", "units": None, "acquisition": {"reference": f"{dates[0]} to {dates[-1]}", "secondary": None},
                  "crs": "EPSG:4326", "status": "prepared", "statusReason": None, "qualityLayerIds": [], "orbitDirection": None, "track": None, "frames": [], "sources": [],
                  "vector": {"url": rel(vec), "type": "line", "color": "#5FE0C9", "opacity": 0.9, "bounds": bounds},
                  "attribution": "Derived by CascadeLens from NISAR GCOV (NASA/JPL-Caltech/ISRO, ASF DAAC)",
                  "limitations": [f"Drawn from radar at {POSTING:.0f} m: edges are accurate to about one or two pixels ({POSTING:.0f} to {2 * POSTING:.0f} m).",
                                  "All dates are drawn on top of each other. Where they overlap, the lake edge did not move."],
                  "sourceGranules": [p.stem for p in files], "productMaturity": "Derived from Provisional data", "page": None}
    lons = [x for f in lake_features for ring in f["geometry"]["coordinates"] for x, _ in ring]
    lats = [y for f in lake_features for ring in f["geometry"]["coordinates"] for _, y in ring]
    lake_box = [min(lons) - 0.01, min(lats) - 0.01, max(lons) + 0.01, max(lats) + 0.01] if lons else bounds
    b = [{**bm, "bounds": lake_box if bm["id"] == "lake" else bounds} for bm in cfg["bookmarks"]]
    if lons:
        b[0]["anchor"] = {"lng": round(float(np.mean([min(lons), max(lons)])), 5), "lat": round(float(np.mean([min(lats), max(lats)])), 5), "label": "Middle of the lake"}
    m = {"schemaVersion": 1, "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fixture": False, "fixtureLabel": None,
            "caseStudy": {"id": case, "name": cfg["name"], "eventDate": dates[-1], "searchEnvelope": bounds},
            "bookmarks": b, "groups": [], "granules": granules, "layers": [backdrop_layer, hh_layer, rgb_layer, lake_layer],
            "lake": {"name": cfg["lake"]["name"], "basin": cfg["lake"]["basin"], "published": cfg["lake"].get("published"), "series": series,
                     "terrain": terrain, "imageSize": [crop[3] - crop[2], crop[1] - crop[0]], "imageMetres": [(crop[3] - crop[2]) * POSTING, (crop[1] - crop[0]) * POSTING], "changeKm2": round(change, 3), "methodHalfRangeKm2": round(spread, 3),
                     "method": f"Dark area in HH + HV below {THRESHOLD_DB:.0f} dB after {FILTER}x{FILTER} smoothing on a {POSTING:.0f} m grid. The range reruns it at {THRESHOLD_RANGE[0]:.0f} and {THRESHOLD_RANGE[1]:.0f} dB."}}
    if pair_folders:
        grid = {"x0": x0, "y0": y0, "rows": rows, "cols": cols, "posting": POSTING, "transform": transform}
        m = motion.add_motion(m, cfg, pair_folders, public, work, grid, np.any(np.stack(lakes), axis=0))
    return m


def nisar_maturity(ident: dict) -> str:
    doi = str(ident.get("productDoi") or "")
    name = {"B": "Beta", "P": "Provisional", "V": "Validated"}.get(doi.rsplit("-", 1)[-1][:1], "Provisional per file name")
    return f"{name} ({ident.get('compositeReleaseId') or 'P05023'})"
