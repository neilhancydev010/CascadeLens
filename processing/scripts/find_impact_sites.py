"""Find and test candidate "cliff impact" sites along the Rasuwa flow path. HYPOTHESIS only.

usage: python find_impact_sites.py
Source of the idea: a mentor, oral communication, no location or figures given.
Uses only data already in the repository: the Simulate flow path, the Copernicus GLO-30 clip, the UNOSAT mudflow extent,
OSM rivers, Pair B (Track 98) coherence and the REACH Sentinel-1 change screening.
Writes data/qa/rasuwa-2026-impact-sites.csv, data/qa/rasuwa-2026-impact-sites.md and frontend/public/data/vectors/impact_sites.json.
The logic is in processing/src/cascade_lens/impact.py.
"""
import csv
import json
import math
import pathlib
import sys

import numpy as np
import rasterio
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform as shp_transform, unary_union

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import impact  # noqa: E402

DATA = ROOT / "frontend/public/data"
UTM = "EPSG:32645"
fwd = Transformer.from_crs("EPSG:4326", UTM, always_xy=True)
back = Transformer.from_crs(UTM, "EPSG:4326", always_xy=True)
SOURCE = "a mentor, oral communication, no location or figures given"
RIVER_NEAR_M = 150.0
BANK_RADIUS_M = 300.0


def vectors(name):
    return json.loads((DATA / f"vectors/{name}.geojson").read_text(encoding="utf8"))["features"]


def to_utm(geom):
    return shp_transform(lambda x, y, z=None: fwd.transform(x, y), geom)


class Dem:
    def __init__(self, path):
        with rasterio.open(path) as src:
            self.z = src.read(1, masked=True).filled(np.nan).astype(float)
            self.inv = ~src.transform
            lat = (src.bounds.top + src.bounds.bottom) / 2
            dx = src.res[0] * 111320 * math.cos(math.radians(lat))
            dy = src.res[1] * 110574
        gy, gx = np.gradient(self.z, dy, dx)
        self.s = np.degrees(np.arctan(np.hypot(gx, gy)))

    def _at(self, grid, x, y):
        lng, lat = back.transform(x, y)
        c, r = self.inv * (lng, lat)
        r, c = r - 0.5, c - 0.5
        r0, c0 = int(math.floor(r)), int(math.floor(c))
        if not (0 <= r0 < grid.shape[0] - 1 and 0 <= c0 < grid.shape[1] - 1):
            return math.nan
        fr, fc = r - r0, c - c0
        return float(grid[r0, c0] * (1 - fr) * (1 - fc) + grid[r0 + 1, c0] * fr * (1 - fc) + grid[r0, c0 + 1] * (1 - fr) * fc + grid[r0 + 1, c0 + 1] * fr * fc)

    def height(self, x, y):
        v = self._at(self.z, x, y)
        return v if math.isfinite(v) else 1e9  # outside the clip: never the river, never a wall

    def slope(self, x, y):
        v = self._at(self.s, x, y)
        return v if math.isfinite(v) else 0.0


def radar(sites, extent):
    """Pair B coherence and REACH Sentinel-1 change on the outer and inner bank of each site (descriptive only)."""
    coh_path = DATA / "sampling/pair-b/gunw-coherence_f016.tif"
    val_path = DATA / "sampling/pair-b/gunw-coherence_f016_validity.tif"
    change = unary_union([to_utm(shape(f["geometry"])) for f in vectors("impact_s1_change")]).buffer(0)
    analysed = unary_union([to_utm(shape(f["geometry"])) for f in vectors("impact_analyzed_area")]).buffer(0)
    with rasterio.open(coh_path) as a, rasterio.open(val_path) as v:
        coh, ok, tr = a.read(1), v.read(1), a.transform
    rows, cols = np.mgrid[:coh.shape[0], :coh.shape[1]]
    xs, ys = rasterio.transform.xy(tr, rows.ravel(), cols.ravel())
    xs, ys = np.asarray(xs).reshape(coh.shape), np.asarray(ys).reshape(coh.shape)
    for s in sites:
        # The side of each pixel: positive on the flow's left. The outer bank is the opposite side of the turn.
        dx, dy = xs - s.x, ys - s.y
        near = (np.hypot(dx, dy) <= BANK_RADIUS_M) & (np.hypot(dx, dy) > impact.DEM_CELL_M)
        out = {}
        # Pixels are split by the line through the apex square to the line towards the centre of the bend circle.
        cx, cy = getattr(s, "_centre", (s.x, s.y))
        toward_centre = (cx - s.x) * dx + (cy - s.y) * dy  # > 0: inner side (towards the centre of the bend)
        for bank, sel in (("outer", near & (toward_centre < 0)), ("inner", near & (toward_centre > 0))):
            good = sel & (ok == 1)
            vals = coh[good]
            zone = Point(s.x, s.y).buffer(BANK_RADIUS_M)
            # The half-disc on this bank, for the REACH overlap
            if (cx, cy) != (s.x, s.y):
                n = math.hypot(cx - s.x, cy - s.y)
                ux, uy = (cx - s.x) / n, (cy - s.y) / n
                sgn = 1 if bank == "inner" else -1
                from shapely.geometry import Polygon
                big = 2 * BANK_RADIUS_M
                half = Polygon([(s.x - uy * big, s.y + ux * big), (s.x + uy * big, s.y - ux * big),
                                (s.x + uy * big + sgn * ux * big, s.y - ux * big + sgn * uy * big), (s.x - uy * big + sgn * ux * big, s.y + ux * big + sgn * uy * big)])
                zone = zone.intersection(half)
            a = zone.area
            out[bank] = {"cohPixels": int(sel.sum()), "cohValid": int(good.sum()), "cohMedian": round(float(np.median(vals)), 3) if vals.size else None,
                         "s1AnalysedPct": round(100 * zone.intersection(analysed).area / a, 1) if a else None,
                         "s1ChangePct": round(100 * zone.intersection(change).area / a, 1) if a else None,
                         "inExtentPct": round(100 * zone.intersection(extent).area / a, 1) if a else None}
        s.radar = out


def write_md(path, sites, rows, cols):
    c = impact.assess.control
    count = {o: sum(1 for s in sites if s.outcome == o) for o in (impact.SUPPORTS, impact.NOT_SHOWN, impact.CANNOT)}
    ix = {k: cols.index(k) for k in cols}
    fmt = lambda v: "" if v is None or v == "" else str(v)  # noqa: E731
    lines = [
        "# Rasuwa: candidate \"cliff impact\" sites (Hypothesis)",
        "",
        f"Source of the idea: {SOURCE}. The mentor said the water hit a cliff edge and \"ricocheted at double the force and the other way\". "
        "CascadeLens tests where it could have happened. It does not confirm that it did.",
        "",
        "Built by `processing/scripts/find_impact_sites.py` from data already in the repository: the Simulate flow path, the Copernicus GLO-30 clip "
        "(30 m, from before the event), the UNOSAT mudflow extent (preliminary, not field validated), OSM rivers, Pair B (Track 98) coherence and the "
        "REACH Sentinel-1 change screening. Every measured input is in `rasuwa-2026-impact-sites.csv`. The method and the physics are in "
        "[docs/SCENARIO_WORKING.md](../../docs/SCENARIO_WORKING.md).",
        "",
        "## Result",
        "",
        f"{len(sites)} bends of at least 45 degrees within 1.5 km have an outer bank of at least 35 degrees within 300 m. Outcomes, by the fixed rules: "
        f"**{count[impact.SUPPORTS]}** where the data support a hard outer-bank impact, **{count[impact.NOT_SHOWN]}** where the data do not show it, "
        f"**{count[impact.CANNOT]}** where the data cannot judge.",
        "",
        f"A control matters more than any single site. On {c['sections']} straight cross-sections the mapped extent's edge is {c['leftMinusRightM']} m higher "
        f"on the flow's left than on its right (middle half {c['p25M']} to {c['p75M']} m). Before that control, almost every right-hand bend looked like support and "
        "almost every left-hand bend did not, which is what a one-sided offset would do. The control is taken off each bend. Even after it, the straight stretches "
        f"scatter by about {c['p75M'] - c['p25M']:.0f} m between their quartiles, so a bend's difference of 5 to 20 m is weak evidence on its own. "
        "**No site shows the marks clearly enough to point to one place.** The strongest are listed first below.",
        "",
        "The expected bends: near km 6 the path turns only 37 degrees over 1.5 km and lies about 5 km from any mapped river (it is a straight line joining the "
        "detachment zone and barrier lakes), so it is not a candidate. At km 13 (S1) the path turns 55 degrees against a 60 degree wall, but the extent reaches "
        "about 105 m *higher on the inner bank*: the opposite of superelevation, so the data do not show an outer-bank impact there.",
        "",
        "The run-up bounds (v ≥ √(2g·h_up)) come out at roughly 10 to 30 m/s, even more than 100 km downstream. That is implausibly fast for a flood so far "
        "from its source, which says the extent's edge on the valley walls is not a run-up line: a preliminary outline drawn generously onto the slopes, and a "
        "30 m terrain model, both lift it. Treat those numbers as what the formula gives from these inputs, not as speeds.",
        "",
        "The radar columns are descriptive only. Low coherence on one bank can come from steep slopes, layover, vegetation or water as well as from damage, and the "
        "REACH screening only covers areas around buildings mapped before the event. They do not enter the outcome.",
        "",
        "| Site | km | Turn | Outer bank | Wall slope | R_c (m) | b (m) | Δh raw (m) | Control (m) | Δh (m) | h_up outer (m) | v, superelevation k 5 to 1 (m/s) | v ≥, run-up (m/s) | Coherence outer / inner | Outcome |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    order = sorted(rows, key=lambda r: (r[ix["outcome"]] != impact.SUPPORTS, -(r[ix["dh_m"]] or -1e9)))
    for r in order:
        v = f"{r[ix['v_super_k5_ms']]} to {r[ix['v_super_k1_ms']]}" if r[ix["v_super_k1_ms"]] is not None else "not given"
        lines.append(f"| {r[0]} | {r[1]} | {r[ix['turn_deg']]}° | {r[ix['outer_side']]} | {r[ix['wall_slope_deg']]}° | {fmt(r[ix['rc_m']])} | {fmt(r[ix['b_m']])} | "
                     f"{fmt(r[ix['dh_raw_m']])} | {fmt(r[ix['control_m']])} | {fmt(r[ix['dh_m']])} | {fmt(r[ix['h_up_outer_m']])} | {v} | {fmt(r[ix['v_runup_min_ms']]) or 'not given'} | "
                     f"{fmt(r[ix['coh_outer_median']])} / {fmt(r[ix['coh_inner_median']])} | {r[ix['outcome']]} |")
    lines += ["", "Speeds are what the formulas give from these inputs, not measurements. Where a bend cannot be judged, no speed is given.",
              "Turn: positive is to the left. Outer bank: the side the flow would hit going straight on.", "",
              "## What to ask the mentor", "",
              "1. Where: the village, bridge, river bend or km along the Bhote Koshi or Trishuli.",
              "2. The source: a report (which), a video or photo (where it can be seen), or a field visit (who, when).",
              "3. What \"double\" was compared with: the push on the rock (which physics allows, up to twice that of a flow that simply stops), "
              "the damage seen, or how fast or far the water went (which physics does not allow: water leaving a wall carries less energy than it arrived with).",
              "4. When in the event, and whether it was the water, the mud and boulders, or a landslide into the river.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    sim = json.loads((DATA / "vectors/simulation.json").read_text(encoding="utf8"))
    lnglat = np.array([p[:2] for p in sim["path"]])
    xy = np.column_stack(fwd.transform(lnglat[:, 0], lnglat[:, 1]))
    # The path's own km: one point per km by construction, so km is the position between the stored points
    seg = np.hypot(*np.diff(xy, axis=0).T)
    along = np.concatenate([[0.0], np.cumsum(seg)])
    km_of = lambda d: float(np.interp(d, along, np.arange(len(along))))  # noqa: E731
    dem = Dem(DATA / "sampling/context/copdem_glo30.tif")
    extent = unary_union([to_utm(shape(f["geometry"])) for f in vectors("unosat_mudflow_extent")]).buffer(0)
    rivers = unary_union([to_utm(shape(f["geometry"])) for f in vectors("osm_rivers")])
    on_river = lambda x, y: rivers.distance(Point(x, y)) <= RIVER_NEAR_M  # noqa: E731
    sites = impact.assess(xy, dem.height, dem.slope, extent, on_river, km_of)
    # The centre of each bend circle, for splitting the banks in the radar comparison
    pts, _ = impact.densify(xy)
    w = int(impact.WINDOW_M / impact.STEP_M)
    for s in sites:
        i = int(np.argmin(np.hypot(pts[:, 0] - s.x, pts[:, 1] - s.y)))
        a, b, c = pts[i - w], pts[i], pts[i + w]
        d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
        if abs(d) > 1e-9:
            ux = ((a @ a) * (b[1] - c[1]) + (b @ b) * (c[1] - a[1]) + (c @ c) * (a[1] - b[1])) / d
            uy = ((a @ a) * (c[0] - b[0]) + (b @ b) * (a[0] - c[0]) + (c @ c) * (b[0] - a[0])) / d
            s._centre = (ux, uy)
    radar(sites, extent)
    qa = ROOT / "data/qa"
    cols = ["id", "km", "lng", "lat", "turn_deg", "outer_side", "on_mapped_river", "rc_m", "b_m", "river_m", "wall_slope_deg", "wall_height_m", "inner_slope_deg",
            "sections", "dh_raw_m", "control_m", "dh_m", "h_up_outer_m", "h_up_inner_m", "v_super_k5_ms", "v_super_k1_ms", "v_runup_min_ms",
            "coh_outer_median", "coh_outer_valid", "coh_inner_median", "coh_inner_valid", "s1_change_outer_pct", "s1_change_inner_pct", "s1_analysed_outer_pct", "s1_analysed_inner_pct",
            "outcome", "reasons"]
    out_rows, features = [], []
    for n, s in enumerate(sites, 1):
        lng, lat = back.transform(s.x, s.y)
        ro, ri = s.radar.get("outer", {}), s.radar.get("inner", {})
        row = [f"S{n}", s.km, round(lng, 5), round(lat, 5), s.turn_deg, s.outer_side, int(s.on_mapped_river), s.rc_m, s.b_m, s.river_m, s.wall_slope_deg, s.wall_height_m, s.inner_slope_deg,
               s.sections, s.dh_raw_m, s.bias_m, s.dh_m, s.h_up_m, s.h_up_inner_m, s.v_super[0] if s.v_super else None, s.v_super[1] if s.v_super else None, s.v_runup,
               ro.get("cohMedian"), ro.get("cohValid"), ri.get("cohMedian"), ri.get("cohValid"), ro.get("s1ChangePct"), ri.get("s1ChangePct"), ro.get("s1AnalysedPct"), ri.get("s1AnalysedPct"),
               s.outcome, "; ".join(s.reasons)]
        out_rows.append(row)
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lng, 5), round(lat, 5)]}, "properties": dict(zip(cols, row))})
    with (qa / "rasuwa-2026-impact-sites.csv").open("w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(cols)
        wr.writerows(out_rows)
    (DATA / "vectors/impact_sites.json").write_text(json.dumps({
        "evidenceClass": "Hypothesis", "source": SOURCE,
        "thresholds": {"turnDeg": impact.MIN_TURN_DEG, "withinKm": 2 * impact.WINDOW_M / 1000, "wallSlopeDeg": impact.WALL_SLOPE_DEG, "wallReachM": impact.WALL_REACH_M,
                       "demNoiseM": impact.DEM_NOISE_M, "minResolvedM": impact.MIN_RESOLVED_M, "k": list(impact.K_RANGE)},
        "control": impact.assess.control, "type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=1), encoding="utf8")
    write_md(qa / "rasuwa-2026-impact-sites.md", sites, out_rows, cols)
    for r in out_rows:
        print(r[0], f"km {r[1]}", f"turn {r[4]}", f"wall {r[10]} deg", f"b {r[8]}", f"Rc {r[7]}", f"dh {r[14]}", "->", r[-2], "|", r[-1])
    print(f"{len(sites)} candidate sites; straight-stretch control {impact.assess.control}")


if __name__ == "__main__":
    main()
