"""Write the Simulate mode's features as a flat table, so anyone can re-count any What-if or Flow replay setting by hand.

usage: python export_simulation_features.py [simulation.json] [out.csv]
Defaults: frontend/public/data/vectors/simulation.json to data/qa/rasuwa-2026-simulation-features.csv (and a copy the app links to).

One row per feature: kind, name, km, h, len, lng, lat.
  kind  b = UNOSAT affected building, a = UNOSAT affected road piece, r = OSM road piece, p = OSM named place
  km    the index of the nearest point on the flow path, which has one point per kilometre (so: km along the path, whole numbers)
  h     ground height (Copernicus DEM) minus the river level at that path point, in metres, never below 0
  len   length of a road piece in km (empty for buildings and places)
  lng, lat  the building or place, or the middle of the road piece
The channel pieces of the path itself (kind c) are left out: they are the path, not something reached.

The app's What-if rule (frontend/src/services/simulation.ts, count): a row counts when km <= the reach AND h <= the rise.
Buildings are counted, rows of kind r add their len, places are listed. Flow replay uses only km <= the reach, and kind a for roads.
"""
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
COLUMNS = ["kind", "name", "km", "h", "len", "lng", "lat"]


def rows(sim: dict) -> list[list]:
    out = []
    for f in sim["features"]["features"]:
        p, g = f["properties"], f["geometry"]
        if p["k"] == "c":
            continue
        c = g["coordinates"]
        lng, lat = (c[0], c[1]) if g["type"] == "Point" else ((c[0][0] + c[-1][0]) / 2, (c[0][1] + c[-1][1]) / 2)
        out.append([p["k"], p.get("name", ""), p["km"], p["h"], p.get("len", ""), round(lng, 5), round(lat, 5)])
    return out


def count(table: list[dict], km: float, rise: float | None = None) -> dict:
    """The same rule as count() in simulation.ts, on the table's rows."""
    buildings, road, places = 0, 0.0, []
    for r in table:
        if float(r["km"]) > km or (rise is not None and float(r["h"]) > rise):
            continue
        if r["kind"] == "b":
            buildings += 1
        elif r["kind"] == ("a" if rise is None else "r"):
            road += float(r["len"] or 0)
        elif r["kind"] == "p":
            places.append(r["name"])
    return {"buildings": buildings, "roadKm": road, "places": places}


def main():
    src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "frontend/public/data/vectors/simulation.json"
    dst = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data/qa/rasuwa-2026-simulation-features.csv"
    sim = json.loads(src.read_text(encoding="utf8"))
    body = rows(sim)
    for target in (dst, ROOT / "frontend/public/data/working" / dst.name):
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(COLUMNS)
            w.writerows(body)
    print(f"{len(body)} features to {dst.relative_to(ROOT) if dst.is_relative_to(ROOT) else dst}")


if __name__ == "__main__":
    main()
