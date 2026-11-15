"""Build the Radar Observability layers for one case.

    python prepare_observability.py <manifest.json> <gunw.h5> <baseline_gunw.h5|-> <dem.tif> <vectors dir> <out dir> [zone files...]
        [--also <gunw.h5> <baseline_gunw.h5|->]...

--also adds a neighbouring frame of the same pairs: cells outside the first frame take that frame's flags (combine_frames).

    [--view ID] [--compare FLAGS.tif]

--view ID      An extra viewing direction (another track) beside the main one, for example t98. Layer ids, file names and the
               fragment get the suffix, layer names say the track and pass, and the fragment goes under
               observabilityViews[ID], so the main observability block is left alone. The two views are never merged.
--compare TIF  The main view's reason-flag raster on the same analysis grid (sampling/<case>/observability-flags.tif). Each
               zone then also reports the share usable from this view only, the main view only, both, either and neither.

Writes into <out dir> (laid out like frontend/public): the reason-flag raster for the inspector, map tiles for the two
tasks, and observability-<case>.json, a fragment that merge_observability() folds into the case manifest.
Nothing is downloaded and the source files are only read.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from shapely.geometry import box, shape
from shapely.ops import unary_union

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from cascade_lens import export, observability as ob  # noqa: E402

ZOOM = (8, 12)


def zones_for(manifest: dict, vectors: pathlib.Path, files: list[str]) -> dict:
    z = {f"bookmark:{b['id']}": (b["name"], box(*b["bounds"])) for b in manifest.get("bookmarks", [])}
    for f in files:
        fc = json.loads((vectors / f).read_text(encoding="utf-8"))
        name = fc.get("name") or f.rsplit(".", 1)[0]
        z[f"vector:{f}"] = (name, unary_union([shape(x["geometry"]) for x in fc["features"]]))
    return z


def view_label(meta: dict) -> str:
    """'Track 98, ascending' from the product's own metadata."""
    return f"Track {meta['trackNumber']}, {str(meta['orbitPassDirection']).lower()}"


def take_option(argv: list[str], flag: str) -> str | None:
    if flag not in argv:
        return None
    i = argv.index(flag)
    value = argv[i + 1]
    del argv[i:i + 2]
    return value


def main(argv: list[str]) -> None:
    argv, extra = list(argv), []
    view, compare = take_option(argv, "--view"), take_option(argv, "--compare")
    sfx = f"-{view}" if view else ""
    while "--also" in argv:
        i = argv.index("--also")
        extra.append((pathlib.Path(argv[i + 1]), None if argv[i + 2] == "-" else pathlib.Path(argv[i + 2])))
        del argv[i:i + 3]
    man, gunw, base, dem, vectors, out = (pathlib.Path(a) for a in argv[:6])
    zone_files = argv[6:]
    m = json.loads(man.read_text(encoding="utf-8"))
    case = m["caseStudy"]["id"]
    baseline = None if str(base) == "-" else base
    r = ob.assess(gunw, baseline, dem, m["caseStudy"]["searchEnvelope"])
    flags, tr, epsg = r["flags"], r["transform"], r["epsg"]
    frames = [{"frame": r["meta"]["frameNumber"], "pair": r["pair"], "baselinePair": r["baselinePair"], "granule": gunw.stem,
               "baselineGranule": baseline.stem if baseline else None, "incidenceDeg5to95": r["incidenceDeg"], "sensitivity": r["sensitivity"],
               "cells": int(((flags & ob.OUTSIDE) == 0).sum())}]
    for g2, b2 in extra:
        r2 = ob.assess(g2, b2, dem, m["caseStudy"]["searchEnvelope"])
        if r2["epsg"] != epsg or r2["transform"] != tr:
            raise SystemExit(f"{g2.name} is not on the same analysis grid")
        if r2["pair"] != r["pair"] or r2["baselinePair"] != r["baselinePair"] or r2["meta"]["trackNumber"] != r["meta"]["trackNumber"]:
            raise SystemExit(f"{g2.name} is not the same pairs on the same track; frames of different dates are never combined")
        flags, took = ob.combine_frames(flags, r2["flags"])
        frames.append({"frame": r2["meta"]["frameNumber"], "pair": r2["pair"], "baselinePair": r2["baselinePair"], "granule": g2.stem,
                       "baselineGranule": b2.stem if b2 else None, "incidenceDeg5to95": r2["incidenceDeg"], "sensitivity": r2["sensitivity"], "cells": int(took.sum())})
    granules = [f["granule"] for f in frames] + [f["baselineGranule"] for f in frames if f["baselineGranule"]]
    rel = lambda p: "data/" + p.relative_to(out).as_posix()  # noqa: E731  (paths as the app loads them)

    other = None
    if compare:
        with rasterio.open(compare) as d:
            if d.shape != flags.shape or tuple(d.transform)[:6] != tuple(tr)[:6] or d.crs.to_epsg() != epsg:
                raise SystemExit("--compare raster is not on the same analysis grid")
            other = d.read(1)  # its nodata value has the OUTSIDE bit set, so it classifies as outside, never usable
    flag_tif = export.write_geotiff(out / f"_work/{case}-flags{sfx}.tif", flags, tr, epsg, nodata=ob.FLAG_NODATA,
                                    tags={"SOURCE_FILE": gunw.name, "BASELINE_FILE": baseline.name if baseline else "", "METHOD": "cascade_lens.observability",
                                          "METHOD_VERSION": ob.METHOD_VERSION})
    flag_cog = export.to_cog(flag_tif, out / f"sampling/{case}/observability-flags{sfx}.tif")
    with rasterio.open(flag_cog) as d:
        flag_bounds = [round(v, 9) for v in transform_bounds(d.crs, "EPSG:4326", *d.bounds)]

    zones = zones_for(m, vectors, zone_files)
    layers, summaries, versus = [], {}, {}
    label = view_label(r["meta"])
    tasks = ["disturbance", "movement"] if baseline else ["movement"]
    for task in tasks:
        cls = ob.classify(flags, task, baseline_assessed=baseline is not None)
        tif = export.write_geotiff(out / f"_work/{case}-{task}{sfx}.tif", cls.astype(np.float32), tr, epsg)
        warped, tx, ty = export.warp_to_tile_grid(tif, ZOOM[1])
        table = ["#00000000"] + [c[2] for c in ob.CLASSES[task]]
        rgba = export.colorize_index(np.nan_to_num(warped, nan=0).astype(np.uint8), table)
        folder = out / f"tiles/{case}/observability-{task}{sfx}"
        n = export.write_pyramid(rgba, tx, ty, ZOOM[1], ZOOM[0], folder)
        summaries[task] = {zid: {"name": nm, **ob.summary(cls, ob.zone_mask(g, epsg, tr, cls.shape), task)} for zid, (nm, g) in zones.items()}
        summaries[task]["_case"] = {"name": "Whole case area", **ob.summary(cls, np.ones(cls.shape, bool), task)}
        if other is not None:
            oc = ob.classify(other, task)
            versus[task] = {zid: {"name": nm, **ob.compare_usable(cls, oc, ob.zone_mask(g, epsg, tr, cls.shape))} for zid, (nm, g) in zones.items()}
            versus[task]["_case"] = {"name": "Whole case area", **ob.compare_usable(cls, oc, np.ones(cls.shape, bool))}
        t1, t2 = r["pair"]
        question = "Could a surface change between these dates be seen here?" if task == "disturbance" else "Could ground movement be measured here?"
        layers.append({
            "id": f"{case}:observability-{task}{sfx}", "groupId": None,
            "name": f"Can the radar see it? ({'surface change' if task == 'disturbance' else 'ground movement'})" + (f", {label}" if view else ""),
            "category": "gridded", "mission": "NISAR", "instrument": "L-SAR", "productType": "Derived here", "measurementClass": "derived",
            "measurementType": f"observability-{task}", "kind": "categorical", "units": None,
            "acquisition": {"reference": t1, "secondary": t2}, "orbitDirection": r["meta"]["orbitPassDirection"], "track": r["meta"]["trackNumber"],
            "frames": [f["frame"] for f in frames], "postingM": [40], "crs": f"EPSG:{epsg}", "qualityLayerIds": [], "status": "sampleable", "statusReason": None,
            "sources": [{"frame": r["meta"]["frameNumber"], "granule": gunw.stem, "sourceFilename": gunw.name, "sourceDataset": "reason flags (see observability block)",
                         "bounds": flag_bounds, "sampling": rel(flag_cog),
                         "tiles": {"url": f"{rel(folder)}/{{z}}/{{x}}/{{y}}.png", "minzoom": ZOOM[0], "maxzoom": ZOOM[1], "count": n}}],
            "sourceGranules": granules, "productMaturity": "Derived from Provisional products",
            "attribution": "Derived by CascadeLens from NISAR GUNW (NASA/ISRO) and Copernicus DEM GLO-30",
            "legend": {"type": "categorical", "stops": [c[2] for c in ob.CLASSES[task]], "keys": [{"color": c[2], "label": c[1]} for c in ob.CLASSES[task]]},
            "explanation": {"what": question,
                            "measures": "Each spot gets its reasons kept separate: inside the frame or not, data present and unflagged by the product's own mask or not, hidden by terrain (layover or shadow, from the radar's own viewing angles and the elevation model), and signal quality. Missing inputs are marked Not assessed, never Usable.",
                            "inspect": "Click any spot to see which reasons apply there. Grey and dark areas are not 'no change': they are places the radar could not judge.",
                            "establishes": "Where a NISAR result can be trusted for this task. It does not say whether anything changed."},
            "limitations": ob.LIMITS,
        })
    block = {
        "pair": r["pair"], "baselinePair": r["baselinePair"], "granule": gunw.stem, "baselineGranule": baseline.stem if baseline else None,
        "track": r["meta"]["trackNumber"], "frame": r["meta"]["frameNumber"], "orbit": r["meta"]["orbitPassDirection"], "look": r["meta"]["lookDirection"],
        "compositeReleaseId": r["meta"]["compositeReleaseId"], "productVersion": r["meta"]["productVersion"],
        "methodVersion": r["methodVersion"], "datasets": r["datasets"], "ccFillValue": r["ccFillValue"], "geometryNotAssessedPct": r["geometryNotAssessedPct"],
        "incidenceDeg5to95": r["incidenceDeg"], "losToSensorEastNorth": [round(r["losEast"], 3), round(r["losNorth"], 3)], "geometryHeightM": r["geometryHeightM"],
        "postingM": 40, "flags": {"outside": ob.OUTSIDE, "noData": ob.NODATA, "layover": ob.LAYOVER, "shadow": ob.SHADOW, "lowCoherence": ob.LOWCOH,
                                  "noConnectedComponent": ob.NOCC, "lowBaselineCoherence": ob.LOWBASE, "productMasked": ob.MASKED,
                                  "geometryNotAssessed": ob.GEOM_UNKNOWN, "baselineNoData": ob.BASE_NODATA},
        "classes": {t: [{"code": c[0], "label": c[1], "color": c[2], "meaning": c[3]} for c in ob.CLASSES[t]] for t in tasks},
        "thresholds": ob.THRESHOLDS, "sensitivity": r["sensitivity"], "limitations": ob.LIMITS, "zones": summaries,
        "frames": frames}  # sensitivity above is the first frame's; each frame's own is in frames
    if view:
        block.update({"view": view, "label": label, "layerIds": [l["id"] for l in layers]})
        if versus:
            block["comparedWith"] = {"flags": compare.rsplit("/", 1)[-1], "note": "Share of each zone usable from this view only, from the main view only, from both, from either and from neither. Not usable includes outside the frame and not assessed.",
                                     "zones": versus}
    frag = {"case": case, "layers": layers, **({"observabilityViews": {view: block}} if view else {"observability": block})}
    (out / f"observability-{case}{sfx}.json").write_text(json.dumps(frag, indent=1), encoding="utf-8")
    print(json.dumps({t: summaries[t]["_case"] for t in tasks}), "| look", r["meta"]["lookDirection"], "| los E,N", round(r["losEast"], 3), round(r["losNorth"], 3), "| inc", r["incidenceDeg"])


if __name__ == "__main__":
    main(sys.argv[1:])
