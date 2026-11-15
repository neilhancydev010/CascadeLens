"""Glacial-lake pair products: a coherence layer for the app, and movement bounds kept as research only.

What reaches the app: one GUNW wrapped-interferogram coherence layer on the lake grid. Coherence says where the radar echo stayed
the same between two passes. It does not say how far anything moved.

What does not reach the app (RESEARCH ONLY, written to data/qa by `prepare_lake.py --research-motion`):
- dam_test: the ionosphere-corrected unwrapped phase on the moraine dam against coherent ground 1.5 to 3.5 km away, turned into a
  magnitude bound in centimetres. It is not shown because the phase sign convention and referencing are not established, the
  elevation-correlated troposphere is not modelled (the dam and its reference ring sit at different heights), and one 12-day pair
  cannot be validated.
- glacier_test: GOFF pixel offsets beyond the far end of the lake against stable ground, in radar-geometry components.

Zones are found from the lake itself: the dam is the lake's lowest shore (the outlet from the 3D route), the glacier zone is the
ground beyond the far end of the lake. No glacier outline is loaded, so the glacier zone is approximate.
"""
from __future__ import annotations

import pathlib
import re

import h5py
import numpy as np
from PIL import Image

from . import export, nisar, quality

SPEED_OF_LIGHT = 299_792_458.0
DAM_RADIUS_M = 500
GLACIER_RADIUS_M = 2500
REF_RING_M = (1500, 3500)
MIN_DAM_PIXELS = 5
MIN_REF_PIXELS = 50  # below this, the reference median and spread are not trustworthy and no bound is returned
DAM_COH_MIN, REF_COH_MIN = 0.3, 0.5
GOFF_LAYER = 3  # the largest matching window: smoothest, same choice as the Rasuwa case
GOFF_SNR_MIN = 5.0  # research-only screen for the glacier test; the app's GOFF layers apply no SNR threshold
MIN_GOFF_PIXELS = 20
COH_STOPS = ["#101417", "#2c4a52", "#5fe0c9", "#e9fff9"]
RESEARCH_CAVEATS = [
    "Research only. Not shown in the app.",
    "Magnitude bounds only: the sign convention and phase referencing are not established.",
    "The elevation-correlated troposphere is not modelled; the dam and its reference ring sit at different heights.",
    "One 12-day pair per value, Provisional products, no independent validation.",
]


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


def coherence_clip(path: pathlib.Path, x0: float, y0: float, rows: int, cols: int) -> tuple[np.ndarray, np.ndarray | None]:
    """20 m wrapped-interferogram coherence on the shared lake grid (same pixel centres as the GCOV clip), and its validity
    classes when the wrapped group carries its own mask. Without one, validity is None and the layer says so."""
    with h5py.File(path, "r") as h:
        g = h[f"{nisar.ROOT['GUNW']}/wrappedInterferogram"]
        x, y = g["xCoordinates"][()], g["yCoordinates"][()]
        c0, r0 = int(np.argmin(np.abs(x - x0))), int(np.argmin(np.abs(y - y0)))
        if abs(x[c0] - x0) > 0.5 or abs(y[r0] - y0) > 0.5 or abs(x[1] - x[0] - 20) > 0.01:
            raise ValueError(f"{path.name}: coherence grid does not line up with the lake grid")
        a = g["HH/coherenceMagnitude"][r0:r0 + rows, c0:c0 + cols].astype(np.float32)
        mask = g["mask"][r0:r0 + rows, c0:c0 + cols] if "mask" in g else None
    if a.shape != (rows, cols):
        raise ValueError(f"{path.name}: lake box runs off the edge of the frame")
    a[(a <= 0) | ~np.isfinite(a)] = np.nan
    return a, (quality.gunw_validity(a, mask) if mask is not None else None)


def wavelength_m(h5) -> float | None:
    """Radar wavelength from the product's own centerFrequency (Hz). None when the file does not state it: no guessed value."""
    found = []

    def visit(name, obj):
        if isinstance(obj, h5py.Dataset) and name.rsplit("/", 1)[-1] == "centerFrequency" and "frequencyA" in name:
            found.append(float(np.asarray(obj[()]).ravel()[0]))

    h5["/science/LSAR"].visititems(visit)
    f = next((v for v in found if np.isfinite(v) and v > 0), None)
    return SPEED_OF_LIGHT / f if f else None


def dam_test(path: pathlib.Path, dam: tuple[float, float]) -> dict:
    """RESEARCH ONLY. Ionosphere-corrected unwrapped phase on the dam, minus coherent ground 1.5 to 3.5 km away in the same
    reliably unwrapped component, as a magnitude bound. Refuses rather than guesses when an input is missing or too thin."""
    root = f"{nisar.ROOT['GUNW']}/unwrappedInterferogram"
    with h5py.File(path, "r") as h:
        lam = wavelength_m(h)
        if lam is None:
            return {"ok": False, "reason": "The product does not state its centre frequency, so no wavelength."}
        u = h[root]
        win, (X, Y) = _window(u["xCoordinates"][()], u["yCoordinates"][()], dam[0], dam[1], REF_RING_M[1] + 200)
        ph = u["HH/unwrappedPhase"][win] - u["HH/ionospherePhaseScreen"][win]
        raw_phase = u["HH/unwrappedPhase"][win]
        coh = u["HH/coherenceMagnitude"][win]
        cc = u["HH/connectedComponents"][win]
        cc_fill = nisar.fill_value(u["HH/connectedComponents"], quality.GUNW_CC_FILL_SPEC)
        mask = u["mask"][win] if "mask" in u else None
    if mask is None:
        return {"ok": False, "reason": "The product has no unwrappedInterferogram mask, so pixel validity cannot be checked."}
    md = quality.decode_gunw_mask(mask)
    usable = (~(md["fill"] | md["unusable"]) & np.isfinite(ph) & ~quality.zero_filled_phase(raw_phase)
              & ~quality.unreliable_component(cc, cc_fill))
    d = np.hypot(X - dam[0], Y - dam[1])
    on_dam = usable & (d < DAM_RADIUS_M) & (coh > DAM_COH_MIN)
    if on_dam.sum() < MIN_DAM_PIXELS:
        return {"ok": False, "reason": f"Fewer than {MIN_DAM_PIXELS} valid, coherent, reliably unwrapped pixels on the dam."}
    comp = int(np.bincount(cc[on_dam].astype(np.int64)).argmax())
    on_dam &= cc == comp
    ref = usable & (d > REF_RING_M[0]) & (d < REF_RING_M[1]) & (coh > REF_COH_MIN) & (cc == comp)
    if ref.sum() < MIN_REF_PIXELS:
        return {"ok": False, "reason": f"Only {int(ref.sum())} valid reference pixels in the same component (at least {MIN_REF_PIXELS} needed)."}
    a, b = float(np.median(ph[on_dam])), float(np.median(ph[ref]))
    to_cm = lam / (4 * np.pi) * 100
    diff, noise = abs(a - b) * to_cm, _spread(ph[ref]) * to_cm
    return {"ok": True, "researchOnly": True, "wavelengthM": round(lam, 5), "component": comp, "pixels": int(on_dam.sum()), "refPixels": int(ref.sum()),
            "coherence": round(float(np.median(coh[on_dam])), 2), "magnitudeDifferenceCm": round(diff, 2), "referenceSpreadCm": round(noise, 2),
            "magnitudeBoundCm": round(max(diff + noise, 2 * noise), 1), "exceedsTwiceSpread": bool(diff > 2 * noise)}


def glacier_test(path: pathlib.Path, dam: tuple[float, float], far: tuple[float, float], length: float) -> dict | None:
    """RESEARCH ONLY. GOFF offsets in the zone beyond the far end of the lake against stable ground around the dam, per
    radar-geometry component, for this one pair. No extrapolation beyond the pair's own interval."""
    with h5py.File(path, "r") as h:
        g = h[f"{nisar.ROOT['GOFF']}/pixelOffsets"]
        x, y = g["xCoordinates"][()], g["yCoordinates"][()]
        if not (x[0] < far[0] < x[-1] and y[-1] < far[1] < y[0]):
            return None
        mid = ((dam[0] + far[0]) / 2, (dam[1] + far[1]) / 2)
        win, (X, Y) = _window(x, y, mid[0], mid[1], length / 2 + GLACIER_RADIUS_M + REF_RING_M[1])
        L = f"HH/layer{GOFF_LAYER}"
        rng, az, snr = g[f"{L}/slantRangeOffset"][win], g[f"{L}/alongTrackOffset"][win], g[f"{L}/snr"][win]
        mask = g["mask"][win] if "mask" in g else None
    if not np.isfinite(rng).any():
        return None
    ok = np.ones(rng.shape, bool)
    if mask is not None:
        md = quality.decode_gunw_mask(mask)
        ok = ~(md["fill"] | md["unusable"])
    dd, dfar = np.hypot(X - dam[0], Y - dam[1]), np.hypot(X - far[0], Y - far[1])
    glacier = ok & (dfar < GLACIER_RADIUS_M) & (dd > length + 300) & (snr > GOFF_SNR_MIN)
    ref = ok & (dd > REF_RING_M[0]) & (dd < REF_RING_M[1]) & (dfar > length) & (snr > GOFF_SNR_MIN)
    if glacier.sum() < MIN_GOFF_PIXELS or ref.sum() < MIN_GOFF_PIXELS:
        return None
    t1, t2 = _dates(path.name)
    days = int((np.datetime64(t2) - np.datetime64(t1)).astype(int))
    track, frame, direction = _track_frame(path.name)
    parts = {}
    for name, v in (("range", rng), ("alongTrack", az)):
        diff = abs(float(np.nanmedian(v[glacier]) - np.nanmedian(v[ref])))
        parts[name] = {"differenceM": round(diff, 2), "referenceSpreadM": round(_spread(v[ref]), 2)}
    return {"researchOnly": True, "track": track, "frame": frame, "direction": direction, "dates": [t1, t2], "days": days, "pixels": int(glacier.sum()),
            "snrMin": GOFF_SNR_MIN, "parts": parts, "boundM": round(max(p["differenceM"] + 2 * p["referenceSpreadM"] for p in parts.values()), 2)}


def _gunw_for(cfg: dict, folders: list[pathlib.Path]) -> list[pathlib.Path]:
    files = sorted({p for f in folders for p in pathlib.Path(f).glob("NISAR_L2_*_GUNW_*.h5")})
    return sorted((p for p in files if _track_frame(p.name)[:2] == (cfg["track"], cfg["frame"])), key=lambda p: _dates(p.name))


def add_coherence_layer(m: dict, cfg: dict, folders: list[pathlib.Path], public: pathlib.Path, work: pathlib.Path, grid: dict, lake: np.ndarray) -> dict:
    """Adds the first same-track GUNW pair's coherence as a layer, and lake.coherence (pair, medians over lake and land).
    Leaves the manifest unchanged when no such pair is found."""
    case, epsg = cfg["id"], cfg["epsg"]
    gunw = _gunw_for(cfg, folders)
    if not gunw:
        print("Coherence: no GUNW pair for this track and frame; skipped")
        return m
    x0, y0, rows, cols = grid["x0"], grid["y0"], grid["rows"], grid["cols"]
    rel = lambda p: pathlib.Path(p).relative_to(public.parent).as_posix()  # noqa: E731
    p = gunw[0]
    t1, t2 = _dates(p.name)
    coh, validity = coherence_clip(p, x0, y0, rows, cols)
    shown = coh if validity is None else np.where(validity == quality.VALID, coh, np.nan)
    dataset = f"{nisar.ROOT['GUNW']}/wrappedInterferogram/HH/coherenceMagnitude"
    tif = export.write_geotiff(work / "coherence.tif", coh, grid["transform"], epsg, tags={"SOURCE_FILE": p.name, "SOURCE_DATASET": dataset})
    cog = export.to_cog(tif, public / f"sampling/{case}/coherence.tif")
    vcog = None
    if validity is not None:
        vtif = export.write_geotiff(work / "coherence.validity.tif", validity, grid["transform"], epsg, nodata=255)
        vcog = export.to_cog(vtif, public / f"sampling/{case}/coherence_validity.tif")
    stif = export.write_geotiff(work / "coherence.shown.tif", shown.astype(np.float32), grid["transform"], epsg)
    warped, tx, ty = export.warp_to_tile_grid(stif, cfg["zoom"][1])
    folder = public / f"tiles/{case}/coherence"
    n = export.write_pyramid(export.colorize(warped, COH_STOPS, 0.0, 1.0), tx, ty, cfg["zoom"][1], cfg["zoom"][0], folder)
    terrain = m["lake"].get("terrain")
    if terrain:
        out = public / f"terrain/{case}/coherence.jpg"
        Image.fromarray(export.colorize(shown, COH_STOPS, 0.0, 1.0)[..., :3], "RGB").save(out, quality=90)
        terrain["drapeCoherence"] = rel(out)
    m["lake"]["coherence"] = {"pair": [t1, t2], "granule": p.stem, "sourceDataset": dataset, "maskApplied": validity is not None,
                              "lake": round(float(np.nanmedian(shown[lake])), 2), "land": round(float(np.nanmedian(shown[~lake])), 2),
                              # How much of each the median rests on: the product's water mask usually covers most of a lake
                              "lakeValidPct": None if validity is None else round(100 * float((validity[lake] == quality.VALID).mean()), 1),
                              "landValidPct": None if validity is None else round(100 * float((validity[~lake] == quality.VALID).mean()), 1)}
    hh = next(l for l in m["layers"] if l["id"] == f"{case}:hh")
    limits = ["Provisional data.", "Steep slopes facing away from the radar are dark because of radar shadow, not change.",
              "Twelve days in the monsoon: wet snow and rain lower coherence even on stable ground.",
              "Coherence shows where the surface stayed the same. It is not a measurement of movement."]
    if validity is None:
        limits.append("The product's mask is defined on the 80 m unwrapped grid, not on this 20 m grid, so it is not applied here.")
    layer = {**{k: hh[k] for k in ("groupId", "mission", "instrument", "crs", "qualityLayerIds", "attribution", "productMaturity", "postingM", "frames", "track", "orbitDirection")},
             "id": f"{case}:coherence", "name": f"Ground stability ({t1[8:]}–{t2[8:]} {np.datetime64(t2).astype(object):%b})", "category": "gridded",
             "measurementClass": "measurement", "measurementType": "gunw-coherence", "productType": "GUNW", "kind": "continuous", "units": "1",
             "status": "sampleable", "statusReason": None, "sourceGranules": [p.stem], "acquisition": {"reference": t1, "secondary": t2},
             "sources": [{"frame": cfg["frame"], "granule": p.stem, "sourceFilename": p.name, "sourceDataset": dataset,
                          "bounds": m["caseStudy"]["searchEnvelope"], "sampling": rel(cog), "validity": rel(vcog) if vcog else None,
                          "tiles": {"url": f"{rel(folder)}/{{z}}/{{x}}/{{y}}.png", "minzoom": cfg["zoom"][0], "maxzoom": cfg["zoom"][1], "count": n}}],
             "stats": export.statistics(np.array([0.0, 1.0]), fixed=(0.0, 1.0)),
             "legend": {"type": "continuous", "stops": COH_STOPS, "min": 0, "max": 1, "unit": None, "lowLabel": "Dark: changed, or water", "highLabel": "Bright: unchanged ground"},
             "explanation": {"what": f"How alike the radar echoes were on {t1} and {t2}, from 0 (nothing alike) to 1 (identical).",
                             "measures": "Interferometric coherence. Bare rock and the moraine dam stay bright. Water, moving ice and fresh snow go dark.",
                             "inspect": "Compare the dam at the lake's western end with the ground around it.",
                             "establishes": "Where the surface stayed the same for 12 days. It does not say how far anything moved."},
             "limitations": limits}
    m["layers"] = [l for l in m["layers"] if l["id"] not in (layer["id"], "ref:zones")] + [layer]
    m["lake"].pop("motion", None)  # movement bounds are research only and never part of the app manifest
    print("Coherence:", m["lake"]["coherence"])
    return m


def motion_research(cfg: dict, folders: list[pathlib.Path], grid: dict, lake: np.ndarray, terrain: dict | None) -> dict | None:
    """RESEARCH ONLY: the dam and glacier tests for every pair found, with their caveats. Written to data/qa, never to the app."""
    if not terrain or not terrain.get("outlet"):
        return None
    folders = [pathlib.Path(f) for f in folders]
    gunw = _gunw_for(cfg, folders)
    goff = sorted({p for f in folders for p in f.glob("NISAR_L2_*_GOFF_*.h5")})
    x0, y0, posting = grid["x0"], grid["y0"], grid["posting"]
    oc, orow = terrain["outlet"][:2]
    step = terrain["spacingM"] / posting
    outlet = (x0 + (oc * step + (step - 1) / 2) * posting, y0 - (orow * step + (step - 1) / 2) * posting)
    dam, far, length = zones(lake, x0, y0, posting, outlet)
    return {"case": cfg["id"], "caveats": RESEARCH_CAVEATS,
            "zones": {"damCentreUtm": [round(dam[0], 1), round(dam[1], 1)], "glacierCentreUtm": [round(far[0], 1), round(far[1], 1)],
                      "damRadiusM": DAM_RADIUS_M, "glacierRadiusM": GLACIER_RADIUS_M, "referenceRingM": list(REF_RING_M)},
            "dam": [{"pair": list(_dates(q.name)), "granule": q.stem, **dam_test(q, dam)} for q in gunw],
            "glacier": [r for p in goff if (r := glacier_test(p, dam, far, length))]}
