"""Granule -> QA -> clipped native-grid rasters -> COGs and tiles -> per-source fragments consumed by manifest.py."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import pathlib
from datetime import datetime, timezone

import h5py
import numpy as np
import rasterio
from rasterio.warp import transform_bounds

from . import export, nisar, quality

log = logging.getLogger("cascade_lens")
PIPELINE_VERSION = "0.2.0"
MASK_RULE = {"GUNW": "Mask: water or invalid subswath masked, 255 no data. Phase only: component label 0 masked, 65535 no data.",
             "GOFF": "Mask as GUNW, plus gross outliers flagged at the configured MAD multiple. Raw values kept.",
             "GCOV": "255 no data. 0 masked only when validSamplesSubSwathMaskingApplied is True."}
DERIVED = {"GUNW": ("gunw-phase-iono",)}
GROUP_PRODUCTS = {"GUNW": ("gunw-phase", "gunw-coherence", "gunw-cc", "gunw-iono"),
                  "GOFF": ("goff-range", "goff-azimuth", "goff-snr", "goff-peak"),
                  "GCOV": ("gcov-backscatter",)}


def groups(cfg: dict) -> list[dict]:
    """Observation pairs and GCOV snapshots as one list of (group, product, frames)."""
    out = [{"id": p["id"], "kind": "pair", "product": prod, **{k: p[k] for k in ("direction", "track", "frames", "ref_date", "sec_date")}}
           for p in cfg["pairs"] for prod in p["products"]]
    out += [{"id": s["id"], "kind": "snapshot", "product": "GCOV", "direction": s["direction"], "track": s["track"],
             "frames": s["frames"], "ref_date": s["date"], "sec_date": None} for s in cfg["snapshots"]]
    return out


def select_granules(catalogue: list[dict], cfg: dict) -> list[dict]:
    """Catalogue records for each configured group, frame and processing release. One release only, never mixed."""
    out = []
    for g in groups(cfg):
        for frame in g["frames"]:
            hits = [c for c in catalogue if c["product"] == g["product"] and c["track"] == g["track"] and c["frame"] == frame
                    and c["direction"] == g["direction"] and c["ref_date"] == g["ref_date"] and c["sec_date"] == g["sec_date"]
                    and f"_{cfg['crid']}_" in c["file_id"]]
            if hits:
                out.append({**hits[0], "group": g["id"]})
    return out


def granule_path(raw: pathlib.Path, granule: dict) -> pathlib.Path:
    return raw / "nisar" / f"{granule['file_id']}.h5"


def _read_clip(h5, path, window):
    ds = h5[path]
    return ds[window], ds.attrs.get("_FillValue")


def native_zoom(posting_m: float, lat: float, cap: int) -> int:
    """Tile zoom whose pixel first reaches the native posting. Going finer would only repeat pixels."""
    return min(cap, math.ceil(math.log2(2 * export.ORIGIN * math.cos(math.radians(lat)) / (256 * posting_m))))


def _once(cache: dict, key: str, read):
    if key not in cache:
        cache[key] = read()
    return cache[key]


def extract(h5, mid: str, paths: dict, cfg: dict, window, cache: dict) -> tuple[np.ndarray, np.ndarray]:
    """Returns (float32 measurement on the native grid, uint8 validity)."""
    product = nisar.MEASUREMENTS[mid]["product"]
    raw, fill = _read_clip(h5, paths[mid], window)
    values = quality.clean(raw, fill)
    root = nisar.ROOT[product]
    mask_path = f"{root}/{nisar.MASK_PATH[product]}"
    mask = None
    if mask_path in h5 and nisar.find_grid(h5, mask_path).same_as(nisar.find_grid(h5, paths[mid])):
        mask = _once(cache, "mask", lambda: h5[mask_path][window])
    if product == "GUNW":
        # Label 0 condemns the phase, not coherence or the component map itself
        cc = _once(cache, "cc", lambda: h5[paths["gunw-cc"]][window]) if mid == "gunw-phase" else None
        return values, quality.gunw_validity(values, mask, cc)
    if product == "GOFF":
        offset = mid in ("goff-range", "goff-azimuth")
        snr = None
        if cfg.get("snr_min") is not None and offset:
            snr = quality.clean(*_read_clip(h5, paths["goff-snr"], window))
        return values, quality.offset_validity(values, cfg["gross_outlier_mad_k"] if offset else None, snr, cfg.get("snr_min"), mask)
    return values, quality.gcov_validity(values, mask, nisar.flag(h5, nisar.GCOV_MASKING_FLAG))


def process_granule(granule: dict, path, cfg: dict, work: pathlib.Path, qa_dir: pathlib.Path) -> tuple[dict, list[dict]]:
    """Returns (status record, per-measurement records). Science outputs exist only if every gate passes."""
    product, layer = granule["product"], cfg["goff_layer"]
    state = {"file_id": granule["file_id"], "group": granule["group"], "product": product, "frame": granule["frame"]}
    report = nisar.inspect(path, product, layer)
    qa_dir.mkdir(parents=True, exist_ok=True)
    (qa_dir / f"{granule['file_id']}.inspection.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    checks = quality.check_granule(report, granule)
    state |= {"status": "inspected", "checks": checks, "sha256": export.sha256(path), "identification": report["identification"]}
    if not quality.passed(checks):
        return state | {"status": "invalid", "reason": "Metadata or dataset checks failed; see data/qa."}, []

    records = []
    with h5py.File(path, "r") as h5:
        paths = nisar.expected_paths(h5, product, layer)
        ref_grid = nisar.find_grid(h5, paths[GROUP_PRODUCTS[product][0]])
        window = nisar.bbox_to_window(ref_grid, cfg["aoi_bbox"])
        if window is None:
            return state | {"status": "unavailable", "reason": "Granule does not overlap the study area."}, []
        cache: dict = {}
        for mid in GROUP_PRODUCTS[product]:
            grid = nisar.find_grid(h5, paths[mid])
            if not grid.same_as(ref_grid):  # phase and coherence are expected to share a grid; never assume it
                return state | {"status": "invalid", "reason": f"{mid} grid differs from {GROUP_PRODUCTS[product][0]}; alignment not implemented."}, []
            values, validity = extract(h5, mid, paths, cfg, window, cache)
            frac = float((validity == quality.VALID).mean())
            masked = float((validity == quality.MASKED).mean())
            state.setdefault("validFraction", {})[mid] = frac
            tr = grid.transform(window[0].start, window[1].start)
            d = work / granule["group"] / f"f{granule['frame']:03d}"
            tags = {"SOURCE_GRANULE": granule["file_id"], "SOURCE_DATASET": paths[mid]}
            tif = export.write_geotiff(d / f"{mid}.tif", values, tr, grid.epsg, tags=tags)
            vtif = export.write_geotiff(d / f"{mid}.validity.tif", validity, tr, grid.epsg, nodata=255, tags=tags)
            attrs = h5[paths[mid]].attrs
            records.append({"measurement": mid, "group": granule["group"], "frame": granule["frame"], "product": product,
                            "tif": str(tif), "validity": str(vtif), "dataset": paths[mid], "granule": granule["file_id"],
                            "units": nisar._py(attrs.get("units")), "epsg": grid.epsg, "posting_m": [abs(grid.dx), abs(grid.dy)],
                            "shape": list(values.shape), "valid_fraction": frac, "masked_fraction": masked, "sha256": state["sha256"],
                            "dtype": str(h5[paths[mid]].dtype), "clip_window": [window[0].start, window[0].stop, window[1].start, window[1].stop],
                            "polarization": report["polarizations"][:1], "goff_layer": layer if product == "GOFF" else None})
    if product == "GUNW":
        add_iono_removed(records, state, work / granule["group"] / f"f{granule['frame']:03d}")
    primary = state["validFraction"][GROUP_PRODUCTS[product][0]]
    state["checks"].append({"check": "valid-pixel fraction", "ok": primary >= cfg["min_valid_fraction"], "expected": f">= {cfg['min_valid_fraction']}", "found": primary})
    if primary < cfg["min_valid_fraction"]:
        return state | {"status": "invalid", "reason": "Too few valid pixels in the study area."}, []
    return state | {"status": "qa_passed"}, records


def add_iono_removed(records: list[dict], state: dict, folder: pathlib.Path) -> None:
    """Derived layer: phase minus the published ionosphere screen. The ATBD writes phase as a sum that includes an ionosphere
    term, and on real Pair A subtraction cut the scatter in both frames while addition raised it. The source layers stay as they were."""
    by = {r["measurement"]: r for r in records}
    p, i = by["gunw-phase"], by["gunw-iono"]
    with rasterio.open(p["tif"]) as a, rasterio.open(i["tif"]) as b, rasterio.open(p["validity"]) as va, rasterio.open(i["validity"]) as vb:
        values, ca, cb, tr, epsg = a.read(1) - b.read(1), va.read(1), vb.read(1), a.transform, a.crs.to_epsg()
    cls = np.where((ca == quality.NODATA) | (cb == quality.NODATA), quality.NODATA, np.where((ca == quality.MASKED) | (cb == quality.MASKED), quality.MASKED, quality.VALID)).astype(np.uint8)
    mid = "gunw-phase-iono"
    tags = {"SOURCE_GRANULE": p["granule"], "SOURCE_DATASET": f"{p['dataset']} minus ionospherePhaseScreen"}
    tif = export.write_geotiff(folder / f"{mid}.tif", values, tr, epsg, tags=tags)
    vtif = export.write_geotiff(folder / f"{mid}.validity.tif", cls, tr, epsg, nodata=255, tags=tags)
    frac = float((cls == quality.VALID).mean())
    state["validFraction"][mid] = frac
    records.append({**p, "measurement": mid, "tif": str(tif), "validity": str(vtif), "dataset": tags["SOURCE_DATASET"], "valid_fraction": frac, "masked_fraction": float((cls == quality.MASKED).mean())})


def _frame_median(r: dict) -> float:
    with rasterio.open(r["tif"]) as a, rasterio.open(r["validity"]) as v:
        d = a.read(1)[v.read(1) == quality.VALID]
    return float(np.median(d)) if d.size else 0.0


def _stack_valid(records: list[dict], transform=None) -> np.ndarray:
    parts = []
    for r in records:
        with rasterio.open(r["tif"]) as a, rasterio.open(r["validity"]) as v:
            d = a.read(1)[v.read(1) == quality.VALID]
        parts.append(transform(d) if transform else d)
    return np.concatenate(parts)


def finalize_layer(mid: str, records: list[dict], cfg: dict, public: pathlib.Path, prepared: pathlib.Path) -> dict:
    """COGs and tiles for every frame of one layer, all drawn with one shared display range."""
    m = nisar.MEASUREMENTS[mid]
    group = records[0]["group"]
    db = m.get("display") == "db"
    relative = m.get("display") == "relative"  # Frames are unwrapped separately, so their absolute levels are not comparable
    fixed = (0.0, 1.0) if mid in ("gunw-coherence", "goff-peak") else None
    if m["kind"] == "categorical":
        labels = sorted({int(x) for x in np.unique(_stack_valid(records)) if np.isfinite(x)})
        stats = {"count": sum(int(r["valid_fraction"] * np.prod(r["shape"])) for r in records), "labels": labels[:64]}
    else:
        stats = export.statistics(_stack_valid(records, quality.to_db if db else ((lambda d: d - np.median(d)) if relative else None)), symmetric=m["colormap"] == "diverging", fixed=fixed)
    stops = export.COLORMAPS[m["colormap"]]
    zmin, cap = cfg["tile_zoom"]
    zmax = max(zmin, native_zoom(records[0]["posting_m"][0], sum(cfg["aoi_bbox"][1::2]) / 2, cap))
    sources = []
    for r in records:
        tag = f"f{r['frame']:03d}"
        cog = export.to_cog(r["tif"], public / "sampling" / group / f"{mid}_{tag}.tif")
        vcog = export.to_cog(r["validity"], public / "sampling" / group / f"{mid}_{tag}_validity.tif")
        grid, x0, y0 = export.warp_to_tile_grid(r["tif"], zmax, validity_path=r["validity"])
        offset = _frame_median(r) if relative else 0.0
        shown = quality.to_db(grid) if db else grid - offset
        if m["kind"] == "categorical":
            rgba = export.colorize_categorical(shown, stops)
        else:
            rgba = export.colorize(shown, stops, stats["displayMin"], stats["displayMax"])
        tiles = public / "tiles" / group / mid / tag
        n = export.write_pyramid(rgba, x0, y0, zmax, zmin, tiles)
        cls, x0, y0 = _validity_grid(r["validity"], zmax)
        n += export.write_pyramid(export.colorize_index(cls, export.COLORMAPS["validity"]), x0, y0, zmax, zmin, tiles.with_name(f"{tag}_mask"))
        with rasterio.open(r["tif"]) as src:
            b = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
        rel = lambda p: pathlib.Path(p).relative_to(public.parent).as_posix()  # noqa: E731
        sources.append({"frame": r["frame"], "granule": r["granule"], "sourceFilename": f"{r['granule']}.h5", "sourceDataset": r["dataset"],
                        "sha256": r["sha256"], "bounds": list(b), "shape": r["shape"], "validFraction": r["valid_fraction"], "maskedFraction": r["masked_fraction"],
                        "sourceDtype": r["dtype"], "clipWindow": r["clip_window"], "displayOffset": offset,
                        "sampling": rel(cog), "validity": rel(vcog), "tiles": {"url": f"{rel(tiles)}/{{z}}/{{x}}/{{y}}.png", "minzoom": zmin, "maxzoom": zmax, "count": n},
                        "maskTiles": f"{rel(tiles.with_name(tag + '_mask'))}/{{z}}/{{x}}/{{y}}.png"})
    fragment = {"layerId": f"{group}:{mid}", "group": group, "measurement": mid, "units": records[0]["units"], "epsg": records[0]["epsg"],
                "postingM": records[0]["posting_m"], "polarization": records[0]["polarization"], "goffLayer": records[0]["goff_layer"],
                "stats": stats, "stops": stops, "displayDb": db, "displayRelative": relative, "sources": sources, "processedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "parameters": {k: cfg[k] for k in ("gross_outlier_mad_k", "snr_min", "coherence_threshold", "goff_layer", "crid", "aoi_bbox")},
                "provenance": {"pipelineVersion": PIPELINE_VERSION, "configSha256": hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest(),
                               "outputDtype": "float32", "validityClasses": {"0": "no data", "1": "valid", "2": "masked"}, "maskRule": MASK_RULE[records[0]["product"]],
                               "tileResampling": "nearest", "nativeGridKept": True, "displayTransform": "10*log10" if db else ("value minus frame median" if relative else None)}}
    prepared.mkdir(parents=True, exist_ok=True)
    (prepared / f"{group}__{mid}.json").write_text(json.dumps(fragment, indent=1), encoding="utf-8")
    return fragment


def _validity_grid(path, zmax):
    """Nearest-neighbour class raster on the tile grid, masked class kept for the overlay."""
    with rasterio.open(path) as src:
        bbox = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
        x0, y0, x1, y1 = export.tile_range(bbox, zmax)
    cls = export.warp_classes(path, export._mercator_transform(x0, y0, zmax), ((y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256))
    return cls, x0, y0
