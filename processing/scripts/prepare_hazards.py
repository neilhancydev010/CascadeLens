"""Terrain landslide screening and road-corridor exposure for one case, on the Radar Observability grid.

    python prepare_hazards.py <manifest.json> <dem.tif> <observability-flags.tif> <vectors dir> <out dir> [--other-view ID FLAGS.tif]

--other-view adds a second viewing direction's flags (prepare_observability.py --view, same grid). Each stretch then also
records the share usable from that view and from either view. The main rating (radarWatch) stays the main view's own.

Writes into <out dir> (laid out like frontend/public): the factor-flag raster for the inspector, map tiles, a road
segment GeoJSON, and hazards-<case>.json, a fragment that merge_observability.py folds into the manifest.
Reads only files already prepared; downloads nothing.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.warp import transform_bounds
from shapely.geometry import LineString, mapping, shape
from shapely.ops import substring, transform as stransform, unary_union

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from cascade_lens import export, hazard as hz, observability as ob  # noqa: E402

ZOOM = (8, 12)
SEG_M = 250
BUFFER_M = 150
RIVER_M = 100
ROAD_TYPES = {"trunk", "primary", "secondary", "tertiary"}
EXPOSURE = [("High", "#D9483B"), ("Moderate", "#E8B04A"), ("Low", "#7FB8A8")]


def segment_id(props: dict, geometry: dict, index: int) -> str:
    """'way/123:4' is the 5th 250 m stretch of OSM way 123, counted from the way's first vertex. Without an OSM ID, a hash of
    the rounded source geometry stands in, so the ID stays the same as long as the road's shape does."""
    if props.get("id"):
        return f"{props['id']}:{index}"
    import hashlib
    coords = json.dumps([[round(x, 5), round(y, 5)] for x, y, *_ in geometry["coordinates"]])
    return f"geom-{hashlib.sha1(coords.encode()).hexdigest()[:12]}:{index}"


def read_fc(p: pathlib.Path):
    return json.loads(p.read_text(encoding="utf-8"))["features"]


def main(argv: list[str]) -> None:
    argv = list(argv)
    other_id = other_path = None
    if "--other-view" in argv:
        i = argv.index("--other-view")
        other_id, other_path = argv[i + 1], pathlib.Path(argv[i + 2])
        del argv[i:i + 3]
    man, dem, flags_path, vectors, out = (pathlib.Path(a) for a in argv[:5])
    m = json.loads(man.read_text(encoding="utf-8"))
    case = m["caseStudy"]["id"]
    rel = lambda p: "data/" + p.relative_to(out).as_posix()  # noqa: E731

    with rasterio.open(flags_path) as d:
        tr, crs, shp, epsg = d.transform, d.crs, d.shape, d.crs.to_epsg()
        obs_flags, obs_nodata = d.read(1), d.nodata
    if obs_nodata is None:
        raise ValueError(f"{flags_path.name} declares no nodata value, so unassessed cells cannot be told apart")
    posting = tr.a
    z = hz.to_grid(dem, tr, crs, shp)
    r = hz.screen(z, posting)
    cls = hz.classify(r["flags"])

    to_utm = Transformer.from_crs(4326, epsg, always_xy=True).transform
    to_ll = Transformer.from_crs(epsg, 4326, always_xy=True).transform
    def poly(name):
        return unary_union([stransform(to_utm, shape(f["geometry"])) for f in read_fc(vectors / name)])
    det, flow = poly("unosat_detachment_zone.geojson"), poly("unosat_mudflow_extent.geojson")
    burn = lambda g: rasterize([(mapping(g), 1)], out_shape=shp, transform=tr, fill=0, dtype="uint8").astype(bool)  # noqa: E731
    in_det, in_flow = burn(det), burn(flow)
    seen = obs_flags != obs_nodata
    valid = (cls > 0) & seen
    score = cls.astype(float)
    validation = {
        "kind": "One-event consistency check, not a validation",
        "caveats": ["One event only: the UNOSAT 2026 detachment zone.", "Every unmapped pixel is treated as a confirmed negative, which it is not.",
                    "Neighbouring pixels are not independent, so the AUC has no meaningful sample size.", "Pixels with no valid elevation (class 0) are left out."],
        "detachmentZone": {"pixels": int((in_det & valid).sum()),
                           "percentByClass": {c[1]: round(100 * float(((cls == c[0]) & in_det & valid).sum()) / max(1, (in_det & valid).sum()), 1) for c in hz.CLASSES},
                           "aucVsRestOfArea": hz.auc(score, in_det & valid, valid & ~in_det & ~in_flow)},
        "mudflowRunout": {"pixels": int((in_flow & valid).sum()),
                          "percentByClass": {c[1]: round(100 * float(((cls == c[0]) & in_flow & valid).sum()) / max(1, (in_flow & valid).sum()), 1) for c in hz.CLASSES},
                          "note": "The runout is where debris travelled and settled, mostly valley floors. A terrain screen for slope failure is not expected to rank it high."},
        "wholeArea": {c[1]: round(100 * float((cls[cls > 0] == c[0]).mean()), 1) for c in hz.CLASSES},
    }
    if validation["detachmentZone"]["aucVsRestOfArea"] is not None:
        validation["detachmentZone"]["aucVsRestOfArea"] = round(validation["detachmentZone"]["aucVsRestOfArea"], 3)

    f_tif = export.write_geotiff(out / f"_work/{case}-terrain-flags.tif", r["flags"], tr, epsg, nodata=255, tags={"SOURCE_FILE": dem.name, "METHOD": "cascade_lens.hazard"})
    f_cog = export.to_cog(f_tif, out / f"sampling/{case}/terrain-screen-flags.tif")
    with rasterio.open(f_cog) as d:
        f_bounds = [round(v, 9) for v in transform_bounds(d.crs, "EPSG:4326", *d.bounds)]
    c_tif = export.write_geotiff(out / f"_work/{case}-terrain-class.tif", cls.astype(np.float32), tr, epsg)
    warped, tx, ty = export.warp_to_tile_grid(c_tif, ZOOM[1])
    rgba = export.colorize_index(np.nan_to_num(warped, nan=0).astype(np.uint8), ["#00000000"] + [c[2] for c in hz.CLASSES])
    rgba[..., 3] = np.where(rgba[..., 3] > 0, 200, 0).astype(np.uint8)
    folder = out / f"tiles/{case}/terrain-screen"
    n = export.write_pyramid(rgba, tx, ty, ZOOM[1], ZOOM[0], folder)

    # Road corridor exposure, 250 m segments
    rivers = unary_union([stransform(to_utm, shape(f["geometry"])) for f in read_fc(vectors / "osm_rivers.geojson") if f["properties"].get("waterway") == "river"])
    hit = unary_union([stransform(to_utm, shape(f["geometry"])) for f in read_fc(vectors / "unosat_affected_roads.geojson")]).buffer(30)
    # Whether the radar could watch a stretch needs the disturbance task, which exists only with a pre-event baseline pair
    has_baseline = bool((m.get("observability") or {}).get("baselinePair"))
    disturb = ob.classify(obs_flags, "disturbance") if has_baseline else np.full(obs_flags.shape, 6, np.uint8)
    other = None
    if other_path:
        view = (m.get("observabilityViews") or {}).get(other_id) or {}
        if not view.get("baselinePair"):
            raise SystemExit(f"view {other_id} has no pre-event pair in the manifest, so it cannot judge change; merge its fragment first")
        with rasterio.open(other_path) as d:
            if d.shape != shp or tuple(d.transform)[:6] != tuple(tr)[:6] or d.crs.to_epsg() != epsg:
                raise SystemExit(f"{other_path.name} is not on the main view's grid")
            other = ob.classify(d.read(1), "disturbance")
    rate = lambda u: "Radar can watch" if u >= 50 else "Partly watchable" if u >= 20 else "Radar cannot watch"  # noqa: E731
    feats, tally = [], {}
    inv = ~tr
    for f in read_fc(vectors / "osm_roads.geojson"):
        props = f["properties"]
        kind = props.get("highway")
        if kind not in ROAD_TYPES or f["geometry"]["type"] != "LineString":
            continue
        line = stransform(to_utm, shape(f["geometry"]))
        for i in range(int(np.ceil(line.length / SEG_M))):
            seg = substring(line, i * SEG_M, min((i + 1) * SEG_M, line.length))
            if seg.length < 20:
                continue
            g = seg.buffer(BUFFER_M)
            x0, y1 = inv * (g.bounds[0], g.bounds[1])
            x1, y0 = inv * (g.bounds[2], g.bounds[3])
            r0, r1, c0, c1 = max(0, int(y0)), min(shp[0], int(y1) + 1), max(0, int(x0)), min(shp[1], int(x1) + 1)
            if r1 <= r0 or c1 <= c0:
                continue
            wt = tr * rasterio.Affine.translation(c0, r0)
            win = rasterize([(mapping(g), 1)], out_shape=(r1 - r0, c1 - c0), transform=wt, fill=0, dtype="uint8").astype(bool)
            inside = win & seen[r0:r1, c0:c1]
            if not inside.any():
                continue
            cl, sc = cls[r0:r1, c0:c1][inside], disturb[r0:r1, c0:c1][inside]
            oc = other[r0:r1, c0:c1][inside] if other is not None else None
            steep = hz.steep_share(cl)  # class 0 (no valid elevation) is left out, never counted as gentle
            steep_n = steep or 0.0
            usable = round(100 * float((sc == 1).mean()), 1)
            hidden = round(100 * float((sc == 3).mean()), 1)
            unseen = round(100 * float(np.isin(sc, (4, 5, 6)).mean()), 1)
            share = lambda k: round(100 * float((sc == k).mean()), 1)  # noqa: E731  one figure per observability class, for the road inspector
            near_river = bool(seg.distance(rivers) <= RIVER_M) if not rivers.is_empty else False
            mapped = bool(seg.intersects(flow)) or bool(seg.intersects(hit))
            reasons = []
            if mapped:
                reasons.append("Crosses ground UNOSAT mapped as hit by the 2026 mudflow")
            if steep is None:
                reasons.append(f"Terrain not assessed: no valid elevation within {BUFFER_M} m")
            elif steep >= 30:
                reasons.append(f"{steep:.0f}% of the ground within {BUFFER_M} m screens High or Very high for slope failure")
            elif steep >= 10:
                reasons.append(f"{steep:.0f}% of nearby ground screens High or Very high")
            if near_river:
                reasons.append(f"Within {RIVER_M} m of a mapped river (OpenStreetMap)")
            level = "High" if mapped or steep_n >= 30 else "Moderate" if steep_n >= 10 or near_river else "Low"
            watch = "Not assessed" if not has_baseline else rate(usable)
            km = seg.length / 1000
            t = tally.setdefault(level, {"km": 0.0, "unwatchedKm": 0.0, **({"unwatchedEitherKm": 0.0} if oc is not None else {})})
            t["km"] += km
            if watch == "Radar cannot watch":
                t["unwatchedKm"] += km
            views = {}
            if oc is not None:
                o_usable = round(100 * float((oc == 1).mean()), 1)
                either = round(100 * float(((sc == 1) | (oc == 1)).mean()), 1)
                views = {"radarOtherView": other_id, "radarOtherUsablePct": o_usable, "radarEitherUsablePct": either, "radarWatchEither": rate(either)}
                if rate(either) == "Radar cannot watch":
                    t["unwatchedEitherKm"] += km
            feats.append({"type": "Feature", "geometry": mapping(stransform(to_ll, seg)), "properties": {
                # Stable ID (E6): the OSM way and the stretch's place along it, so a report row can be traced back
                "id": segment_id(props, f["geometry"], i), "osmId": props.get("id"), "name": props.get("name_en") or props.get("name"),
                "bridge": props.get("bridge"), "osmStatus": props.get("status"), "road": kind, "exposure": level, "color": dict(EXPOSURE)[level], "reasons": reasons,
                "steepSharePct": steep, "nearRiver": near_river, "mapped2026": mapped,
                "radarWatch": watch, "radarUsablePct": usable, "radarHiddenPct": hidden, "radarUnseenPct": unseen,
                "radarUnreliablePct": share(2), "radarNoValidPct": share(4), "radarOutsidePct": share(5), "radarNotAssessedPct": share(6), **views,
                "lengthM": round(seg.length)}})
    road_path = out / f"vectors/road-exposure-{case}.geojson"
    road_path.parent.mkdir(parents=True, exist_ok=True)
    road_path.write_text(json.dumps({"type": "FeatureCollection", "name": "Road exposure", "features": feats}), encoding="utf-8")
    xs = [c for f in feats for c in f["geometry"]["coordinates"]]
    road_bounds = [round(min(c[0] for c in xs), 6), round(min(c[1] for c in xs), 6), round(max(c[0] for c in xs), 6), round(max(c[1] for c in xs), 6)]
    for t in tally.values():
        for k in t:
            t[k] = round(t[k], 1)

    base = {"groupId": None, "mission": "Copernicus DEM", "instrument": "TanDEM-X (via Copernicus DEM GLO-30)", "orbitDirection": None, "track": None, "frames": [],
            "qualityLayerIds": [], "status": "sampleable", "statusReason": None, "sourceGranules": [], "productMaturity": "Experimental screen"}
    layers = [{**base, "id": f"{case}:terrain-screen", "name": "Landslide-prone terrain (screen)", "category": "gridded", "productType": "Derived here",
               "measurementClass": "derived", "measurementType": "terrain-screen", "kind": "categorical", "units": None,
               "acquisition": {"reference": "2011-2015 (DEM source campaign)", "secondary": None}, "postingM": [int(posting)], "crs": f"EPSG:{epsg}",
               "sources": [{"frame": None, "granule": "Copernicus DEM GLO-30", "sourceFilename": dem.name, "sourceDataset": "factor flags (see hazards block)",
                            "bounds": f_bounds, "sampling": rel(f_cog), "tiles": {"url": f"{rel(folder)}/{{z}}/{{x}}/{{y}}.png", "minzoom": ZOOM[0], "maxzoom": ZOOM[1], "count": n}}],
               "attribution": "Derived by CascadeLens from Copernicus DEM GLO-30",
               "legend": {"type": "categorical", "stops": [c[2] for c in hz.CLASSES], "keys": [{"color": c[2], "label": c[1]} for c in hz.CLASSES]},
               "explanation": {"what": "Where the shape of the ground favours slope failure: steepness, converging hollows and wet ground.",
                               "measures": "Slope, plan curvature and a topographic wetness index from the elevation model, combined by fixed, published rules.",
                               "inspect": "Click a spot to see which terrain factors apply there.",
                               "establishes": "A screen of terrain only. It is not a forecast, not trained on a Nepal landslide inventory, and leaves out geology, soil and rainfall."},
               "limitations": hz.LIMITS},
              {**base, "id": f"{case}:road-exposure", "name": "Road exposure (screen)", "category": "reference", "mission": "CascadeLens", "instrument": "OpenStreetMap roads + terrain screen + Radar Observability",
               "productType": "Derived here", "measurementClass": "derived", "measurementType": "road-exposure", "kind": "vector", "units": None,
               "acquisition": {"reference": "Event pair 2026-08-16 to 2026-08-28", "secondary": None}, "status": "prepared", "sources": [],
               "vector": {"url": rel(road_path), "type": "line", "color": "#E8B04A", "opacity": 0.95, "bounds": road_bounds, "colorProperty": "color", "width": 3},
               "attribution": "Derived by CascadeLens from OpenStreetMap (ODbL), Copernicus DEM, UNOSAT and NISAR GUNW",
               "legend": {"type": "categorical", "stops": [c for _, c in EXPOSURE], "keys": [{"color": c, "label": f"{l} exposure"} for l, c in EXPOSURE]},
               "limitations": ["A screen, not a risk rating: traffic, road design, retaining walls and drainage are unknown.",
                               "OpenStreetMap roads exported after the event; some may have moved or closed.",
                               "Click a road segment to see why it is rated as it is, and whether the radar can watch it."]}]
    frag = {"case": case, "layers": layers, "hazards": {
        "terrain": {"layerId": layers[0]["id"], "flags": {"slope15to25": hz.STEEP_1, "slope25to35": hz.STEEP_2, "slope35plus": hz.STEEP_3, "hollow": hz.HOLLOW, "wet": hz.WET},
                    "classes": [{"code": c[0], "label": c[1], "color": c[2], "meaning": c[3]} for c in hz.CLASSES], "thresholds": hz.THRESHOLDS,
                    "wetIndexCut": round(r["wetCut"], 2), "validation": validation, "limitations": hz.LIMITS, "maturity": "EXPERIMENTAL"},
        "roads": {"layerId": layers[1]["id"], "segmentM": SEG_M, "bufferM": BUFFER_M, "riverM": RIVER_M, "roadTypes": sorted(ROAD_TYPES), "kmByExposure": tally,
                  "rules": {"High": "Crosses ground mapped as hit in 2026, or 30% or more of the ground within 150 m screens High or Very high",
                            "Moderate": "10% or more screens High or Very high, or within 100 m of a mapped river (OpenStreetMap)", "Low": "Otherwise",
                            "radarWatch": "Share of the 150 m corridor where the event pair could see a surface change: 50% or more = can watch, 20 to 50% = partly, under 20% = cannot",
                            **({"radarWatchEither": f"The same rule on the share usable from either the main view or view {other_id}; the two views are never merged into one reason"} if other is not None else {})},
                  "maturity": "EXPERIMENTAL"},
        "dynamicTrigger": {"maturity": "BLOCKED BY DATA", "needs": ["GPM IMERG daily rainfall for Aug 2026", "SMAP soil moisture", "A Nepal-calibrated rainfall threshold"]}}}
    (out / f"hazards-{case}.json").write_text(json.dumps(frag, indent=1), encoding="utf-8")
    print(json.dumps({"validation": validation, "roads": tally, "segments": len(feats), "tiles": n}))


if __name__ == "__main__":
    main(sys.argv[1:])
