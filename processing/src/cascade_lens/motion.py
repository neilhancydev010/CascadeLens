"""Is the dam or the glacier moving? Two NISAR pair products tested over a glacial lake.

GUNW (interferometry, 12 days): coherence shows where the ground kept the same radar "fingerprint" between passes, and the
unwrapped phase on the dam, compared with the ground around it, bounds how far the dam moved towards or away from the satellite.
GOFF (pixel offsets, 12 days): image matching between two passes, in metres. The glacier zone is compared with stable ground.

Zones are found from the lake itself: the dam is the lake's lowest shore (the outlet from the 3D route), the glacier zone is
the ground beyond the far end of the lake. No glacier outline is loaded, so the glacier zone is approximate.
Results are upper limits ("less than"), not detections, unless the difference clearly exceeds the spread of stable ground.
"""
from __future__ import annotations

import json
import pathlib
import re

import h5py
import numpy as np
from PIL import Image
from rasterio.warp import transform_geom

from . import export, nisar

WAVELENGTH_M = 0.2384  # NISAR L-band, 1257.5 MHz
DAM_RADIUS_M = 500
GLACIER_RADIUS_M = 2500
REF_RING_M = (1500, 3500)
GOFF_LAYER = 3  # the largest matching window: smoothest, same choice as the Rasuwa case
COH_STOPS = ["#101417", "#2c4a52", "#5fe0c9", "#e9fff9"]


def _dates(name: str) -> tuple[str, str]:
    t = re.findall(r"_(\d{8})T\d{6}", name)
    iso = lambda s: f"{s[:4]}-{s[4:6]}-{s[6:]}"  # noqa: E731
    return iso(t[0]), iso(t[2])


def _track_frame(name: str) -> tuple[int, int, str]:
    m = re.search(r"_(GUNW|GOFF)_\d{3}_(\d{3})_([AD])_(\d{3})_", name)
    return int(m.group(2)), int(m.group(4)), "ascending" if m.group(3) == "A" else "descending"


def _spread(v: np.ndarray) -> float:
    return float((np.nanpercentile(v, 84) - np.nanpercentile(v, 16)) / 2)


def zones(lake: np.ndarray, x0: float, y0: float, posting: float, outlet_xy: tuple[float, float]):
    """Dam centre = outlet; glacier centre = the lake pixel farthest from the outlet."""
    r, c = np.nonzero(lake)
    xs, ys = x0 + c * posting, y0 - r * posting
    d = np.hypot(xs - outlet_xy[0], ys - outlet_xy[1])
    i = int(d.argmax())
    return outlet_xy, (float(xs[i]), float(ys[i])), float(d[i])


def _window(x: np.ndarray, y: np.ndarray, cx: float, cy: float, half: float):
    c0, c1 = np.searchsorted(x, cx - half), np.searchsorted(x, cx + half)
    r0, r1 = np.searchsorted(-y, -(cy + half)), np.searchsorted(-y, -(cy - half))
    return np.s_[r0:r1, c0:c1], np.meshgrid(x[c0:c1], y[r0:r1])


def coherence_clip(path: pathlib.Path, x0: float, y0: float, rows: int, cols: int) -> np.ndarray:
    """20 m wrapped-interferogram coherence on the shared lake grid (same pixel centres as the GCOV clip)."""
    with h5py.File(path, "r") as h:
        g = h[f"{nisar.ROOT['GUNW']}/wrappedInterferogram"]
        x, y = g["xCoordinates"][()], g["yCoordinates"][()]
        c0, r0 = int(np.argmin(np.abs(x - x0))), int(np.argmin(np.abs(y - y0)))
        if abs(x[c0] - x0) > 0.5 or abs(y[r0] - y0) > 0.5 or abs(x[1] - x[0] - 20) > 0.01:
            raise ValueError(f"{path.name}: coherence grid does not line up with the lake grid")
        a = g["HH/coherenceMagnitude"][r0:r0 + rows, c0:c0 + cols].astype(np.float32)
    if a.shape != (rows, cols):
        raise ValueError(f"{path.name}: lake box runs off the edge of the frame")
    a[(a <= 0) | ~np.isfinite(a)] = np.nan
    return a


def dam_test(path: pathlib.Path, dam: tuple[float, float], lake_far: float) -> dict:
    """Ionosphere-corrected unwrapped phase on the dam, minus coherent ground 1.5 to 3.5 km away in the same connected component."""
    with h5py.File(path, "r") as h:
        u = h[f"{nisar.ROOT['GUNW']}/unwrappedInterferogram"]
        win, (X, Y) = _window(u["xCoordinates"][()], u["yCoordinates"][()], dam[0], dam[1], REF_RING_M[1] + 200)
        ph = u["HH/unwrappedPhase"][win] - u["HH/ionospherePhaseScreen"][win]
        coh = u["HH/coherenceMagnitude"][win]
        cc = u["HH/connectedComponents"][win]
    d = np.hypot(X - dam[0], Y - dam[1])
    on_dam = (d < DAM_RADIUS_M) & (coh > 0.3) & np.isfinite(ph)
    if on_dam.sum() < 5:
        return {"ok": False, "reason": "Too few coherent radar pixels on the dam."}
    comp = int(np.bincount(cc[on_dam].astype(int)).argmax())
    on_dam &= cc == comp
    ref = (d > REF_RING_M[0]) & (d < REF_RING_M[1]) & (coh > 0.5) & (cc == comp) & np.isfinite(ph)
    a, b = float(np.median(ph[on_dam])), float(np.median(ph[ref]))
    to_cm = WAVELENGTH_M / (4 * np.pi) * 100
    diff, noise = abs(a - b) * to_cm, _spread(ph[ref]) * to_cm
    return {"ok": True, "pixels": int(on_dam.sum()), "refPixels": int(ref.sum()), "coherence": round(float(np.median(coh[on_dam])), 2),
            "differenceCm": round(diff, 2), "noiseCm": round(noise, 2), "limitCm": round(max(diff + noise, 2 * noise), 1),
            "detected": bool(diff > 2 * noise)}


def glacier_test(path: pathlib.Path, dam: tuple[float, float], far: tuple[float, float], length: float) -> dict | None:
    """GOFF offsets in the zone beyond the far end of the lake against stable ground around the dam."""
    with h5py.File(path, "r") as h:
        g = h[f"{nisar.ROOT['GOFF']}/pixelOffsets"]
        x, y = g["xCoordinates"][()], g["yCoordinates"][()]
        if not (x[0] < far[0] < x[-1] and y[-1] < far[1] < y[0]):
            return None
        mid = ((dam[0] + far[0]) / 2, (dam[1] + far[1]) / 2)
        win, (X, Y) = _window(x, y, mid[0], mid[1], length / 2 + GLACIER_RADIUS_M + REF_RING_M[1])
        L = f"HH/layer{GOFF_LAYER}"
        rng, az, snr = g[f"{L}/slantRangeOffset"][win], g[f"{L}/alongTrackOffset"][win], g[f"{L}/snr"][win]
    if not np.isfinite(rng).any():
        return None
    dd, dfar = np.hypot(X - dam[0], Y - dam[1]), np.hypot(X - far[0], Y - far[1])
    glacier = (dfar < GLACIER_RADIUS_M) & (dd > length + 300) & (snr > 5)
    ref = (dd > REF_RING_M[0]) & (dd < REF_RING_M[1]) & (dfar > length) & (snr > 5)
    if glacier.sum() < 20 or ref.sum() < 20:
        return None
    t1, t2 = _dates(path.name)
    days = (np.datetime64(t2) - np.datetime64(t1)).astype(int)
    track, frame, direction = _track_frame(path.name)
    parts = {}
    for name, v in (("range", rng), ("alongTrack", az)):
        diff = abs(float(np.nanmedian(v[glacier]) - np.nanmedian(v[ref])))
        parts[name] = {"differenceM": round(diff, 2), "noiseM": round(_spread(v[ref]), 2)}
    limit = max(p["differenceM"] + 2 * p["noiseM"] for p in parts.values())
    return {"track": track, "frame": frame, "direction": direction, "dates": [t1, t2], "days": int(days), "pixels": int(glacier.sum()),
            "parts": parts, "limitM": round(limit, 2), "perYearM": round(limit * 365 / days), "detected": any(p["differenceM"] > 2 * p["noiseM"] + 0.1 for p in parts.values())}


def _circle(cx: float, cy: float, r: float, epsg: int) -> dict:
    t = np.linspace(0, 2 * np.pi, 49)
    ring = [[float(cx + r * np.cos(a)), float(cy + r * np.sin(a))] for a in t]
    return transform_geom(f"EPSG:{epsg}", "EPSG:4326", {"type": "LineString", "coordinates": ring})


def add_motion(m: dict, cfg: dict, folders: list[pathlib.Path], public: pathlib.Path, work: pathlib.Path, grid: dict, lake: np.ndarray) -> dict:
    """Adds the coherence layer, the zone outlines and manifest.lake.motion. Leaves the manifest as it was if no pair files are found."""
    case, epsg = cfg["id"], cfg["epsg"]
    x0, y0, rows, cols, posting = grid["x0"], grid["y0"], grid["rows"], grid["cols"], grid["posting"]
    files = sorted({p for f in folders for p in pathlib.Path(f).glob("NISAR_L2_*_G*_*.h5")})
    gunw = sorted((p for p in files if "_GUNW_" in p.name and _track_frame(p.name)[:2] == (cfg["track"], cfg["frame"])), key=lambda p: _dates(p.name))
    goff = [p for p in files if "_GOFF_" in p.name]
    terrain = m["lake"].get("terrain") or {}
    if not (gunw or goff) or not terrain.get("outlet"):
        print("Movement: no GUNW/GOFF files for this lake, or no 3D route to place the dam; skipped")
        return m
    oc, orow = terrain["outlet"][:2]
    step = terrain["spacingM"] / posting
    outlet = (x0 + (oc * step + (step - 1) / 2) * posting, y0 - (orow * step + (step - 1) / 2) * posting)
    dam, far, length = zones(lake, x0, y0, posting, outlet)
    rel = lambda p: pathlib.Path(p).relative_to(public.parent).as_posix()  # noqa: E731
    motion: dict = {"wavelengthCm": round(WAVELENGTH_M * 100, 1), "glacier": [], "zonesNote": "The dam zone is a 500 m circle at the lake's lowest shore. The glacier zone is a 2.5 km circle beyond the far end of the lake. No glacier outline is loaded, so this zone is approximate."}
    layers = []
    if gunw:
        p = gunw[0]
        t1, t2 = _dates(p.name)
        coh = coherence_clip(p, x0, y0, rows, cols)
        motion["pair"] = [t1, t2]
        motion["dam"] = dam_test(p, dam, length)
        motion["damPairs"] = [{"pair": list(_dates(q.name)), **dam_test(q, dam, length)} for q in gunw]
        motion["coherenceLake"] = round(float(np.nanmedian(coh[lake])), 2)
        motion["coherenceLand"] = round(float(np.nanmedian(coh[~lake])), 2)
        transform = grid["transform"]
        tif = export.write_geotiff(work / "coherence.tif", coh, transform, epsg, tags={"SOURCE_FILE": p.name, "SOURCE_DATASET": f"{nisar.ROOT['GUNW']}/wrappedInterferogram/HH/coherenceMagnitude"})
        cog = export.to_cog(tif, public / f"sampling/{case}/coherence.tif")
        warped, tx, ty = export.warp_to_tile_grid(tif, cfg["zoom"][1])
        folder = public / f"tiles/{case}/coherence"
        n = export.write_pyramid(export.colorize(warped, COH_STOPS, 0.0, 1.0), tx, ty, cfg["zoom"][1], cfg["zoom"][0], folder)
        if terrain:
            out = public / f"terrain/{case}/coherence.jpg"
            rgba = export.colorize(coh, COH_STOPS, 0.0, 1.0)
            Image.fromarray(rgba[..., :3], "RGB").save(out, quality=90)
            terrain["drapeCoherence"] = rel(out)
        hh = next(l for l in m["layers"] if l["id"] == f"{case}:hh")
        layers.append({**{k: hh[k] for k in ("groupId", "mission", "instrument", "crs", "qualityLayerIds", "attribution", "productMaturity", "postingM", "frames", "track", "orbitDirection")},
                       "id": f"{case}:coherence", "name": f"Ground stability ({t1[8:]}–{t2[8:]} {np.datetime64(t2).astype(object):%b})", "category": "gridded",
                       "measurementClass": "measurement", "measurementType": "gunw-coherence", "productType": "GUNW", "kind": "continuous", "units": "1",
                       "status": "sampleable", "statusReason": None, "sourceGranules": [p.stem], "acquisition": {"reference": t1, "secondary": t2},
                       "sources": [{"frame": cfg["frame"], "granule": p.stem, "sourceFilename": p.name, "sourceDataset": f"{nisar.ROOT['GUNW']}/wrappedInterferogram/HH/coherenceMagnitude",
                                    "bounds": m["caseStudy"]["searchEnvelope"], "sampling": rel(cog), "validity": None,
                                    "tiles": {"url": f"{rel(folder)}/{{z}}/{{x}}/{{y}}.png", "minzoom": cfg["zoom"][0], "maxzoom": cfg["zoom"][1], "count": n}}],
                       "stats": export.statistics(np.array([0.0, 1.0]), fixed=(0.0, 1.0)),
                       "legend": {"type": "continuous", "stops": COH_STOPS, "min": 0, "max": 1, "unit": None, "lowLabel": "Dark: changed, or water", "highLabel": "Bright: unchanged ground"},
                       "explanation": {"what": f"How alike the radar echoes were on {t1} and {t2}, from 0 (nothing alike) to 1 (identical).",
                                       "measures": "Interferometric coherence. Bare rock and the moraine dam stay bright. Water, moving ice and fresh snow go dark.",
                                       "inspect": "Look at the dam at the lake's western end: if it were slumping or soaking it would turn dark.",
                                       "establishes": "Where the surface stayed the same for 12 days. It does not say how far anything moved."},
                       "limitations": ["Provisional data.", "Steep slopes facing away from the radar are dark because of radar shadow, not change.",
                                       "Twelve days in the monsoon: wet snow and rain lower coherence even on stable ground."]})
    for p in goff:
        r = glacier_test(p, dam, far, length)
        if r:
            motion["glacier"].append(r)
    zone_file = public / f"vectors/{case}-zones.geojson"
    zone_file.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"zone": "dam"}, "geometry": _circle(*dam, DAM_RADIUS_M, epsg)},
        {"type": "Feature", "properties": {"zone": "glacier"}, "geometry": _circle(*far, GLACIER_RADIUS_M, epsg)}]}), encoding="utf-8")
    layers.append({"id": "ref:zones", "groupId": None, "name": "Dam and glacier zones tested for movement", "category": "reference", "mission": "NISAR", "instrument": "L-SAR",
                   "productType": "Derived here", "measurementClass": "derived", "measurementType": "reference", "kind": "vector", "units": None,
                   "acquisition": {"reference": motion.get("pair", ["", ""])[0], "secondary": None}, "crs": "EPSG:4326", "status": "prepared", "statusReason": None,
                   "qualityLayerIds": [], "orbitDirection": None, "track": None, "frames": [], "sources": [],
                   "vector": {"url": rel(zone_file), "type": "line", "color": "#FF7F66", "opacity": 0.95, "dash": True, "bounds": m["caseStudy"]["searchEnvelope"]},
                   "attribution": "Derived by CascadeLens", "limitations": [motion["zonesNote"]], "sourceGranules": [], "productMaturity": "Derived", "page": None})
    m["layers"] = [l for l in m["layers"] if l["id"] not in {x["id"] for x in layers}] + layers
    m["lake"]["motion"] = motion
    print("Movement:", json.dumps({k: v for k, v in motion.items() if k != "zonesNote"}))
    return m
