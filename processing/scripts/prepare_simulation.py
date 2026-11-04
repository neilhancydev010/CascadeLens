"""Prepare the Simulate mode's data for any event: the flow path along the rivers, and how far and how high each mapped feature sits from it.

usage: python prepare_simulation.py [config.json]   (default: the Rasuwa config. See docs/ADDING_DATA.md)
Paths in the config are relative to frontend/public/data, or to "dataRoot" if it sets one. Needs "dem", "rivers" and "start".
"via", "mainRivers", "buildings", "affectedRoads", "roads" and "places" are optional. "start" is a file or [lng, lat].
No hydrology here: the path is geometry and the heights are terrain.
"""
import heapq
import json
import math
import pathlib
import sys

import numpy as np
import rasterio

ROOT = pathlib.Path(__file__).resolve().parents[2]
RASUWA = ROOT / "processing/configs/simulation/rasuwa-2026.json"

SIDE_COST = 5  # Rivers outside "mainRivers" only bridge gaps in the main stem
JOIN_KM = 0.4  # OSM reaches often stop short of each other
NEAR_KM = 2  # Features further than this from the path are in another valley
RIVER_WINDOW = 4  # Pixels either side: mapped lines sit off the true channel, so take the lowest ground nearby


def centre(geometry):
    def points(c):
        return [c] if isinstance(c[0], (int, float)) else [p for x in c for p in points(x)]

    pts = points(geometry["coordinates"])
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def lines_of(geometry):
    return {"LineString": [geometry["coordinates"]], "MultiLineString": geometry["coordinates"]}.get(geometry["type"], [])


class Terrain:
    def __init__(self, path):
        with rasterio.open(path) as src:
            self.dem = src.read(1, masked=True).filled(np.nan).astype(float)
            self.inverse = ~src.transform

    def cell(self, p):
        col, row = self.inverse * tuple(p[:2])
        return int(min(max(row, 0), self.dem.shape[0] - 1)), int(min(max(col, 0), self.dem.shape[1] - 1))

    def height(self, p):
        return float(self.dem[self.cell(p)])

    def river(self, p):
        r, c = self.cell(p)
        window = self.dem[max(r - RIVER_WINDOW, 0):r + RIVER_WINDOW + 1, max(c - RIVER_WINDOW, 0):c + RIVER_WINDOW + 1]
        return float(np.nanmin(window)) if np.isfinite(window).any() else math.nan


def walk(rivers, main, km, top):
    """Cheapest walk along the rivers from one point to everywhere reachable, staying on the main stem wherever it can."""
    edges = {}

    def link(a, b, cost):
        edges.setdefault(a, []).append((b, cost))
        edges.setdefault(b, []).append((a, cost))

    ends = []
    for f in rivers:
        factor = 1 if not main or f["properties"].get("label", f["properties"].get("name")) in main else SIDE_COST
        for coords in lines_of(f["geometry"]):
            line = [tuple(p[:2]) for p in coords]
            for a, b in zip(line, line[1:]):
                link(a, b, km(a, b) * factor)
            ends += [line[0], line[-1]]
    nodes = list(edges)
    for a in ends:
        for b in nodes:
            if a != b and km(a, b) < JOIN_KM:
                link(a, b, km(a, b) * SIDE_COST)
    best, before, heap = {top: 0.0}, {}, [(0.0, top)]
    while heap:
        cost, here = heapq.heappop(heap)
        if cost > best[here]:
            continue
        for there, step in edges[here]:
            if cost + step < best.get(there, math.inf):
                best[there], before[there] = cost + step, here
                heapq.heappush(heap, (cost + step, there))
    return best, before


def resample(line, km, step=1.0):
    """A point every kilometre along the line, so a list index is a distance."""
    out, done, target = [line[0]], 0.0, step
    for a, b in zip(line, line[1:]):
        size = km(a, b)
        while done + size >= target and size:
            t = (target - done) / size
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            target += step
        done += size
    return out


def build(cfg, data):
    def vectors(key):
        return json.loads((data / cfg[key]).read_text(encoding="utf8"))["features"] if cfg.get(key) else []

    terrain = Terrain(data / cfg["dem"])
    rivers = vectors("rivers")
    main = set(cfg.get("mainRivers", []))
    start = tuple(cfg["start"]) if isinstance(cfg["start"], list) else centre(vectors("start")[0]["geometry"])
    lat = math.radians(start[1])
    km_lng, km_lat = 111.32 * math.cos(lat), 110.9  # Good to about 1% across one corridor

    def km(a, b):
        return math.hypot((a[0] - b[0]) * km_lng, (a[1] - b[1]) * km_lat)

    via = sorted((centre(f["geometry"]) for f in vectors("via")), key=lambda p: km(p, start))
    stem = [tuple(p[:2]) for f in rivers if not main or f["properties"].get("label", f["properties"].get("name")) in main for c in lines_of(f["geometry"]) for p in c]
    if not stem:
        raise SystemExit("No river in the rivers file matches mainRivers")
    # ponytail: straight lines to the first mapped river, because nothing maps a channel there. A DEM flow route would replace it.
    top = min(stem, key=lambda p: km(p, via[-1] if via else start))
    best, before = walk(rivers, main, km, top)
    reachable = [p for p in best if not math.isnan(terrain.height(p))]
    bottom = min(reachable, key=lambda p: (terrain.height(p), -best[p]))  # The flow runs to the lowest river ground it can reach
    line = [bottom]
    while line[-1] != top:
        line.append(before[line[-1]])
    points = resample([start, *via, *line[::-1]], km)
    levels = np.fmin.accumulate([terrain.river(p) for p in points])  # Water does not run uphill

    pts = np.array(points)
    features = []
    rounded = lambda p: [round(p[0], 5), round(p[1], 5)]

    def emit(kind, geometry, p, **extra):
        near = np.hypot((pts[:, 0] - p[0]) * km_lng, (pts[:, 1] - p[1]) * km_lat)
        i = int(near.argmin())
        if near[i] > NEAR_KM or math.isnan(terrain.height(p)):
            return None
        props = {"k": kind, "km": i, "h": max(round(terrain.height(p) - float(levels[i])), 0), **extra}
        features.append({"type": "Feature", "properties": props, "geometry": geometry})
        return props

    for i, (a, b) in enumerate(zip(points, points[1:])):
        features.append({"type": "Feature", "properties": {"k": "c", "km": i, "h": 0}, "geometry": {"type": "LineString", "coordinates": [rounded(a), rounded(b)]}})
    buildings = vectors("buildings")
    for f in buildings:
        p = centre(f["geometry"])
        emit("b", {"type": "Point", "coordinates": rounded(p)}, p)
    places = []
    for f in vectors("places"):
        p = centre(f["geometry"])
        props = emit("p", {"type": "Point", "coordinates": rounded(p)}, p, name=f["properties"].get("label", f["properties"].get("name", "Unnamed")))
        if props:
            places.append({"name": props["name"], "km": props["km"], "h": props["h"]})

    def split(kind, key):
        total = 0.0
        for f in vectors(key):
            for coords in lines_of(f["geometry"]):
                for a, b in zip(coords, coords[1:]):
                    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                    if emit(kind, {"type": "LineString", "coordinates": [rounded(a), rounded(b)]}, mid, len=round(km(a, b), 3)):
                        total += km(a, b)
        return round(total, 1)

    mapped = split("a", "affectedRoads")
    roads = split("r", "roads")
    return {
        "path": [[*rounded(p), round(float(z))] for p, z in zip(points, levels)],
        "places": sorted(places, key=lambda x: x["km"]),
        "features": {"type": "FeatureCollection", "features": features},
        "totals": {"buildings": sum(f["properties"]["k"] == "b" for f in features), "buildingsAll": len(buildings), "mappedRoadKm": mapped, "roadKm": roads},
    }


def main():
    config = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else RASUWA
    cfg = json.loads(config.read_text(encoding="utf8"))
    data = ROOT / "frontend/public/data"
    if cfg.get("dataRoot"):
        data = (config.parent / cfg["dataRoot"]).resolve()
    out = build(cfg, data)
    target = ROOT / "frontend/public/data" / cfg["output"]
    target.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
    print(f"{len(out['path']) - 1} km path, {out['path'][0][2]} m to {out['path'][-1][2]} m, {len(out['features']['features'])} features, {target.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
