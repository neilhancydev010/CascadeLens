"""Road access screen for one case (audit P0.4), from the HOT OpenStreetMap export and the HOT bridge damage assessment.

    python prepare_access.py <access config.json> <raw context dir> <public data dir> <out dir>

Reads data/raw/context (fetch_context.py) and the case's road-exposure stretches; downloads nothing. Writes, laid out like
frontend/public: vectors/access-states-<case>.geojson (ways with a reported state), vectors/facilities-<case>.geojson
(health facilities and helipads), and access-<case>.json, a fragment merge_observability.py folds into the manifest.

Three networks are compared, all from the same mapped roads:
  before    every mapped road, including those OSM now maps as destroyed (the closest thing to the pre-event network)
  reported  roads mapped as destroyed and bridges reported washed out are closed
  screen    as reported, and also every stretch on ground UNOSAT mapped as hit in 2026 (hypothetical, to direct checks)
"""
from __future__ import annotations

import glob
import json
import math
import pathlib
import sys
import zipfile

import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import transform as stransform

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from cascade_lens import access as ax  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_COLOR = {"closed": "#D9483B", "uncertain": "#E8B04A", "open": "#7FB8A8", "unknown": "#8a8f98"}


def read(raw: pathlib.Path, key: str) -> gpd.GeoDataFrame:
    f = sorted(glob.glob(str(raw / key / "*")))[0]
    if f.endswith(".zip"):
        name = next(n for n in zipfile.ZipFile(f).namelist() if n.endswith(".gpkg"))
        return gpd.read_file(f"zip://{f}!/{name}")
    return gpd.read_file(f)


def lines_of(geom):
    return [geom] if geom.geom_type == "LineString" else list(getattr(geom, "geoms", []))


def main(cfg_path: str, raw_dir: str, public_dir: str, out_dir: str) -> None:
    cfg = json.loads(pathlib.Path(cfg_path).read_text(encoding="utf-8"))
    raw, public, out = pathlib.Path(raw_dir), pathlib.Path(public_dir), pathlib.Path(out_dir)
    case, src = cfg["case"], cfg["sources"]
    aoi = box(*json.loads((ROOT / "processing/configs/pipeline.json").read_text())["aoi_bbox"])
    to_utm = Transformer.from_crs(4326, cfg["epsg"], always_xy=True).transform
    g = ax.Graph()
    ll_geom: dict[str, object] = {}

    roads = read(raw, src["roads"])
    roads = roads[roads.intersects(aoi) & roads["highway"].isin(ax.DRIVABLE)]
    for r in roads.itertuples():
        for k, part in enumerate(lines_of(r.geometry)):
            wid = r.id if k == 0 else f"{r.id}#{k}"
            g.add_way(wid, [tuple(c) for c in stransform(to_utm, part).coords], highway=r.highway, name=r.name_en if isinstance(r.name_en, str) else (r.name if isinstance(r.name, str) else None),
                      bridge=r.bridge if isinstance(r.bridge, str) else None, mappedNow=True, osmStatus=getattr(r, "status", None))
            ll_geom[wid] = part
            # HOT's export keeps roads OSM now maps as destroyed, with status "Destroyed": closed, with OSM as the source
            if getattr(r, "status", None) == "Destroyed":
                g.set_state(wid, "closed", "OpenStreetMap maps it as destroyed after the 2026 event (HOT export status)")

    # Destroyed features the roads export lacks (mostly destroyed bridges with no highway tag left): added back, closed, so the
    # network before the event is as complete as the mapping allows.
    dest = read(raw, src["destroyed"])
    dest = dest[dest.intersects(aoi) & (dest["destroyed_highway"].isin(ax.DRIVABLE) | dest["destroyed_bridge"].notna())
                & dest.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    n_dest = 0
    for r in dest.itertuples():
        for k, part in enumerate(lines_of(r.geometry)):
            wid = r.id if k == 0 else f"{r.id}#{k}"
            if wid in g.ways:
                continue
            g.add_way(wid, [tuple(c) for c in stransform(to_utm, part).coords], highway=r.destroyed_highway if isinstance(r.destroyed_highway, str) else "bridge",
                      name=r.name_en if isinstance(r.name_en, str) else None, bridge="yes" if isinstance(r.destroyed_bridge, str) else None, mappedNow=False)
            g.set_state(wid, "closed", f"OpenStreetMap maps it as destroyed after the 2026 event ({r.damage_type if isinstance(r.damage_type, str) else 'cause not tagged'})")
            ll_geom[wid] = part
            n_dest += 1

    # Bridge damage points: matched to the nearest way tagged as a bridge, within bridgeMatchM metres
    bridges = read(raw, src["bridges"])
    bridges = bridges[bridges.intersects(aoi)]
    bridge_ways = {w: shape(mapping(stransform(to_utm, ll_geom[w]))) for w, p in g.ways.items() if p.get("bridge")}
    matched, unmatched = [], []
    for b in bridges.itertuples():
        p = shape(mapping(stransform(to_utm, b.geometry)))
        best = min(((geom.distance(p), w) for w, geom in bridge_ways.items()), default=(math.inf, None))
        state = cfg["bridgeStatus"].get(b.status, "unknown")
        rec = {"name": b.name, "status": b.status, "lng": round(b.geometry.x, 6), "lat": round(b.geometry.y, 6)}
        if best[1] is not None and best[0] <= cfg["bridgeMatchM"]:
            g.set_state(best[1], state, f"HOT bridge damage assessment: {b.name}, {b.status}")
            matched.append({**rec, "way": best[1], "distanceM": round(best[0], 1)})
        else:
            unmatched.append({**rec, "nearestBridgeWayM": None if math.isinf(best[0]) else round(best[0])})

    # Anchors: OSM places, health facilities, helipads
    def anchors_of(key, label, named_only=False, keep=None):
        df = read(raw, src[key])
        df = df[df.intersects(aoi)].copy()
        if keep is not None:
            df = df[keep(df)]
        out_ = []
        for r in df.itertuples():
            name = (r.name_en if isinstance(getattr(r, "name_en", None), str) else None) or (r.name if isinstance(r.name, str) else None)
            if name is None and named_only:
                continue  # an unnamed place point cannot be reported to anyone
            name = name or f"{label.capitalize()} (unnamed in OSM, {r.id})"
            pt = r.geometry if r.geometry.geom_type == "Point" else r.geometry.representative_point()
            xy = to_utm(pt.x, pt.y)
            n = g.nearest(xy, cfg["snapM"])
            out_.append({"name": name, "id": r.id, "kind": label, "lng": round(pt.x, 6), "lat": round(pt.y, 6), "node": n,
                         "snapM": None if n is None else round(math.dist(xy, g.xy[n]))})
        return out_

    places = [a for a in anchors_of("places", "place", named_only=True) if a["name"].isascii()]
    health = anchors_of("health", "health facility", keep=lambda df: df["amenity"].isin(cfg["healthAmenities"]) | df["healthcare"].isin(cfg["healthAmenities"]))
    helipads = anchors_of("helipads", "helipad")
    # Two places may share a name (OSM has two Adamghat points): keep both, told apart by their OSM ID
    seen: dict[str, int] = {}
    for a in places:
        seen[a["name"]] = seen.get(a["name"], 0) + 1
    for a in places:
        if seen[a["name"]] > 1:
            a["name"] = f"{a['name']} ({a['id']})"
    closed_reported = {w for w, p in g.ways.items() if p["state"] == "closed"}
    stretches = json.loads((public / f"vectors/road-exposure-{case}.geojson").read_text(encoding="utf-8"))["features"]
    hit = {s["properties"]["osmId"] for s in stretches if s["properties"].get("mapped2026") and s["properties"].get("osmId") in g.ways}
    scenarios = [
        {"id": "before", "name": "Every mapped road open", "closed": set(),
         "meaning": "Includes roads OSM now maps as destroyed: the closest thing to the network before the event."},
        {"id": "reported", "name": "Reported damage closed", "closed": closed_reported,
         "meaning": "Roads OSM maps as destroyed and bridges reported washed out are closed. Everything else, reported or not, is left open."},
        {"id": "screen", "name": "Also close every stretch on ground mapped as hit", "closed": closed_reported | hit,
         "meaning": "Hypothetical. Adds every road the exposure screen found on ground UNOSAT mapped as hit in 2026, to show which places depend on them."},
    ]
    # Two questions that do not depend on one chosen hub: how far each place is from its nearest health facility (and helipad)
    # by road, and which places still share a connected piece of the network.
    def nearest(targets, s):
        dist, prev, origin = ax.nearest_source(g, {a["name"]: a["node"] for a in targets if a["node"] is not None}, s["closed"])
        out_ = {}
        for p in places:
            n = p["node"]
            if n is None:
                out_[p["name"]] = {"path": False, "reason": "No mapped road within reach of this place"}
            elif math.isinf(dist[n]):
                out_[p["name"]] = {"path": False, "reason": "No road path in this network"}
            else:
                ways = ax.path_ways(prev, n)
                st = [g.ways[w]["state"] for w in ways]
                out_[p["name"]] = {"path": True, "km": round(dist[n] / 1000, 2), "to": origin[n], "ways": ways,
                                   "uncertainWays": st.count("uncertain"), "unknownWays": st.count("unknown")}
        return out_

    def changes_of(before, after, closed):
        out_ = {}
        for name, b in before.items():
            a = after[name]
            if not b["path"]:
                out_[name] = {"change": "no path in either", "reason": b["reason"]}
            elif not a["path"]:
                out_[name] = {"change": "no path", "beforeKm": b["km"], "beforeTo": b["to"]}
            elif a["km"] > b["km"] + 0.05 or a["to"] != b["to"]:
                out_[name] = {"change": "longer" if a["km"] > b["km"] + 0.05 else "other destination", "beforeKm": b["km"], "beforeTo": b["to"],
                              "km": a["km"], "to": a["to"], "detourKm": round(a["km"] - b["km"], 2)}
            else:
                out_[name] = {"change": "unchanged", "km": a["km"], "to": a["to"]}
            if out_[name]["change"] in ("no path", "longer", "other destination"):  # the closures on the old route, with their sources
                out_[name]["closedOnRoute"] = [{"way": w, "name": g.ways[w].get("name"), "highway": g.ways[w]["highway"], "state": g.ways[w]["state"],
                                                "sources": g.ways[w].get("sources", ["Hypothetical closure (screen)"])} for w in b["ways"] if w in closed]
        return out_

    def strip(r):
        return {k: {kk: vv for kk, vv in v.items() if kk != "ways"} for k, v in r.items()}

    health_r = {s["id"]: nearest(health, s) for s in scenarios}
    heli_r = {s["id"]: nearest(helipads, s) for s in scenarios}
    health_changes = {s["id"]: changes_of(health_r["before"], health_r[s["id"]], s["closed"]) for s in scenarios[1:]}
    heli_changes = {s["id"]: changes_of(heli_r["before"], heli_r[s["id"]], s["closed"]) for s in scenarios[1:]}
    groups = {}
    for s in scenarios:
        lab = ax.pieces(g, s["closed"])
        by: dict[int, list[str]] = {}
        for a in places + health + helipads:
            if a["node"] is not None:
                by.setdefault(lab[a["node"]], []).append(a["name"])
        groups[s["id"]] = sorted((sorted(v) for v in by.values()), key=lambda v: (-len(v), v[0]))

    tally = {st: {"ways": 0, "km": 0.0} for st in ax.STATES}
    for p in g.ways.values():
        tally[p["state"]]["ways"] += 1
        tally[p["state"]]["km"] += p["lengthM"] / 1000
    for t in tally.values():
        t["km"] = round(t["km"], 1)

    feats = [{"type": "Feature", "geometry": mapping(ll_geom[w]), "properties": {
        "id": w, "highway": p["highway"], "name": p.get("name"), "bridge": p.get("bridge"), "state": p["state"], "color": STATE_COLOR[p["state"]],
        "sources": p.get("sources", []), "mappedNow": p["mappedNow"], "closedIn": [s["id"] for s in scenarios if w in s["closed"]]}}
        for w, p in sorted(g.ways.items()) if p["state"] != "unknown" or w in hit]
    vec = out / f"vectors/access-states-{case}.geojson"
    vec.parent.mkdir(parents=True, exist_ok=True)
    vec.write_text(json.dumps({"type": "FeatureCollection", "name": "Road states", "features": feats}), encoding="utf-8")
    fac = out / f"vectors/facilities-{case}.geojson"
    fac.write_text(json.dumps({"type": "FeatureCollection", "name": "Health facilities and helipads", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [a["lng"], a["lat"]]}, "properties": {"id": a["id"], "name": a["name"], "kind": a["kind"]}}
        for a in health + helipads]}), encoding="utf-8")

    bounds = lambda fs: [round(v, 6) for v in gpd.GeoDataFrame.from_features(fs, crs=4326).total_bounds]  # noqa: E731
    rel = lambda p: "data/" + p.relative_to(out).as_posix()  # noqa: E731
    base = {"groupId": None, "category": "reference", "orbitDirection": None, "track": None, "frames": [], "qualityLayerIds": [], "status": "prepared",
            "statusReason": None, "sources": [], "units": None, "kind": "vector", "measurementType": "reference", "crs": "EPSG:4326", "sourceGranules": [], "page": "https://data.humdata.org/dataset/hot_flood_npl"}
    layers = [
        {**base, "id": f"{case}:road-states", "name": "Road and bridge states (reported)", "mission": "OpenStreetMap", "instrument": "HOT export and HOT bridge damage assessment",
         "productType": "Vector", "measurementClass": "reference map", "acquisition": {"reference": "Post-event mapping, 2026", "secondary": None},
         "vector": {"url": rel(vec), "type": "line", "color": "#D9483B", "opacity": 0.95, "bounds": bounds(feats), "colorProperty": "color", "width": 3},
         "attribution": "© OpenStreetMap contributors (ODbL), via HOT; bridge assessment by HOT volunteers",
         "legend": {"type": "categorical", "stops": [STATE_COLOR[s] for s in ("closed", "uncertain", "open")], "keys": [
             {"color": STATE_COLOR["closed"], "label": "Closed: mapped destroyed or reported washed out"},
             {"color": STATE_COLOR["uncertain"], "label": "Uncertain: reported damaged"}, {"color": STATE_COLOR["open"], "label": "Open: reported intact"}]},
         "limitations": ["Reports and mapping, not field verified here. Unmapped damage is not shown: a road with no report is Unknown, not open.",
                         "Bridge reports are points, matched to the nearest OSM bridge within 60 m; unmatched reports are listed in the access block."],
         "productMaturity": "Community-maintained"},
        {**base, "id": f"{case}:facilities", "name": "Health facilities and helipads (OSM)", "mission": "OpenStreetMap", "instrument": "HOT export",
         "productType": "Vector", "measurementClass": "reference map", "acquisition": {"reference": "HOT export, 2026", "secondary": None},
         "vector": {"url": rel(fac), "type": "circle", "color": "#74c0fc", "opacity": 0.95, "radius": 4, "bounds": bounds(json.loads(fac.read_text())["features"])},
         "attribution": "© OpenStreetMap contributors (ODbL), via HOT", "limitations": ["Only facilities mapped in OSM; small health posts may be missing."],
         "productMaturity": "Community-maintained"},
    ]
    detail = {
        "maturity": "EXPERIMENTAL",
        "network": {"ways": len(g.ways), "km": round(sum(p["lengthM"] for p in g.ways.values()) / 1000, 1), "vertices": len(g.xy),
                    "destroyedWaysAdded": n_dest, "classes": sorted(ax.DRIVABLE)},
        "states": tally,
        "bridges": {"reports": len(bridges), "matched": matched, "unmatched": unmatched, "matchWithinM": cfg["bridgeMatchM"]},
        "scenarios": [{k: v for k, v in s.items() if k != "closed"} | {"closedWays": len(s["closed"])} for s in scenarios],
        "anchors": [{k: v for k, v in a.items() if k != "node"} for a in places + health + helipads],
        "nearestHealth": {k: strip(v) for k, v in health_r.items()}, "healthChanges": health_changes,
        "nearestHelipad": {k: strip(v) for k, v in heli_r.items()}, "helipadChanges": heli_changes,
        "pieces": groups,
        "healthDestinations": {"amenities": cfg["healthAmenities"], "why": cfg["healthWhy"]},
        "rules": {"junction": "Ways connect only where they share an OSM vertex; a crossing without one is not a junction.",
                  "snap": f"Each place is joined to the nearest road vertex within {cfg['snapM']} m.",
                  "states": "closed: mapped destroyed or reported washed out; uncertain: reported damaged; open: reported intact; unknown: no report (the default)."},
        "limitations": ["A screen, not a statement about who can be reached: footpaths, river crossings, unmapped tracks and helicopters are outside this network.",
                        "The network stops at the study area. A detour that leaves it, for example through Kathmandu, is not found, so 'no road path in this network' can be a boundary effect.",
                        "Only facilities mapped in OSM inside the study area are destinations: three here. Others, including those just outside, are not counted.",
                        "'No path in either' means the mapped roads do not join even with every road open: a gap in the mapping or the network, not a closure.",
                        "OpenStreetMap is incomplete and was edited after the event; roads may be missing or out of date.",
                        "A road with no report is Unknown. The reported network leaves it open, which may be wrong either way.",
                        "No traffic, road condition, vehicle type or season is modelled; distances are along the mapped centre line."],
    }
    # The detail is fetched by the access panel when opened; the manifest keeps a pointer and a summary, so start-up stays small
    det = out / f"access/{case}.json"
    det.parent.mkdir(parents=True, exist_ok=True)
    det.write_text(json.dumps(detail, separators=(",", ":")), encoding="utf-8")
    frag = {"case": case, "layers": layers, "access": {
        "url": rel(det), "maturity": "EXPERIMENTAL", "states": tally,
        "summary": {s["id"]: {"name": s["name"], "placesWithHealthPath": sum(1 for v in health_r[s["id"]].values() if v["path"]),
                              "places": len(places), "pieces": len(groups[s["id"]])} for s in scenarios},
        "limitations": detail["limitations"]}}
    (out / f"access-{case}.json").write_text(json.dumps(frag, indent=1), encoding="utf-8")
    summary = {s["id"]: {"placesWithHealthPath": sum(1 for v in health_r[s["id"]].values() if v["path"]), "pieces": len(groups[s["id"]])} for s in scenarios}
    print(json.dumps({"ways": len(g.ways), "destroyedAdded": n_dest, "bridgesMatched": len(matched), "bridgesUnmatched": len(unmatched),
                      "states": tally, "summary": summary, "places": len(places), "health": len(health), "helipads": len(helipads)}))


if __name__ == "__main__":
    main(*sys.argv[1:5])
