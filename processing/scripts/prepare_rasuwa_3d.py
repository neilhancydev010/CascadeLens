"""Build the Rasuwa 3D model from files already in the app: NASADEM heights, UNOSAT maps, NISAR coherence and backscatter,
OPERA Sentinel-1 change and OSM context.

usage: python prepare_rasuwa_3d.py
Reads frontend/public/data (manifest, sampling GeoTIFFs, vectors) and writes frontend/public/data/terrain/rasuwa-2026/:
heights.bin (Int16 metres, row by row from the north-west corner), one image per draped layer and model.json.
Every layer carries the evidence class the app gives the same layer on the map, and the manifest's own names, attribution
and limitations, so no caveat is reworded here. Nothing here is a forecast or a warning.
"""
import json
import pathlib

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

ROOT = pathlib.Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "frontend/public/data"
OUT = PUBLIC / "terrain/rasuwa-2026"
CRS = "EPSG:32645"  # UTM 45N, the same grid the NISAR products use
GRID_M = 120  # spacing of the 3D mesh
IMG_M = 50  # pixel size of the draped pictures: sharp enough at this scale, and small enough for slow connections

m = json.loads((PUBLIC / "manifests/manifest.json").read_text(encoding="utf-8"))
L = {l["id"]: l for l in m["layers"]}
west, south, east, north = m["caseStudy"]["searchEnvelope"]
fwd = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
xs, ys = fwd.transform([west, east, west, east], [south, south, north, north])
# The latitude-longitude box is slightly rotated in UTM, so keep the largest upright rectangle inside it: no empty edges
x0, x1 = max(xs[0], xs[2]), min(xs[1], xs[3])
y0, y1 = max(ys[0], ys[1]), min(ys[2], ys[3])
x0, y1 = np.ceil(x0 / GRID_M) * GRID_M, np.floor(y1 / GRID_M) * GRID_M
nx = int((x1 - x0) // GRID_M) + 1
ny = int((y1 - y0) // GRID_M) + 1
span_x, span_y = (nx - 1) * GRID_M, (ny - 1) * GRID_M
iw, ih = int(round(span_x / IMG_M)), int(round(span_y / IMG_M))
img_tf = from_origin(x0, y1, span_x / iw, span_y / ih)
OUT.mkdir(parents=True, exist_ok=True)


def warp(path, shape_, tf, resampling=Resampling.bilinear):
    out = np.full(shape_, np.nan, dtype="float32")
    with rasterio.open(path) as src:
        reproject(rasterio.band(src, 1), out, src_nodata=src.nodata if src.nodata is not None else np.nan, dst_transform=tf, dst_crs=CRS, dst_nodata=np.nan, resampling=resampling)
    return out


# Heights: the mesh samples the DEM at the grid nodes, so the edges sit exactly on the picture edges
dem_path = PUBLIC / "sampling/context/nasadem.tif"  # NASADEM, from prepare_nasa_rasuwa.py
grid_tf = from_origin(x0 - GRID_M / 2, y1 + GRID_M / 2, GRID_M, GRID_M)
z = warp(dem_path, (ny, nx), grid_tf, Resampling.average)
z = np.where(np.isfinite(z), z, np.nanmin(z))
z.round().astype("<i2").tofile(OUT / "heights.bin")

# Base picture: hillshade tinted by height, made from the same DEM at picture resolution (Reference, like the map's terrain)
d = warp(dem_path, (ih, iw), img_tf)
d = np.where(np.isfinite(d), d, np.nanmin(d))
gy, gx = np.gradient(d, IMG_M)
az, alt = np.radians(315), np.radians(40)
slope = np.arctan(np.hypot(gx, gy))
aspect = np.arctan2(-gx, gy)
shade = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
stops = np.array([300, 900, 1600, 2600, 3600, 4600, 5400, 6500])
cols = np.array([[96, 128, 76], [120, 146, 86], [150, 156, 104], [160, 146, 112], [146, 128, 108], [150, 144, 140], [214, 218, 224], [246, 248, 252]], float)
tint = np.stack([np.interp(d, stops, cols[:, k]) for k in range(3)], -1)
base = np.clip(tint * (0.35 + 0.75 * shade[..., None]), 0, 255).astype("uint8")
Image.fromarray(base).save(OUT / "base.jpg", quality=80, optimize=True, progressive=True)


def vector_png(layer_id, name, color, opacity, line_px=0):
    gj = json.loads((ROOT / "frontend/public" / L[layer_id]["vector"]["url"]).read_text(encoding="utf-8"))
    geoms = []
    for f in gj["features"]:
        g = shape(f["geometry"])
        if g.is_empty:
            continue
        g = shp_transform(lambda a, b, c=None: fwd.transform(a, b), g)
        if line_px:
            g = g.buffer(line_px * IMG_M / 2)
        geoms.append(g)
    mask = rasterize(((g, 1) for g in geoms), out_shape=(ih, iw), transform=img_tf, fill=0, dtype="uint8", all_touched=True)
    rgba = np.zeros((ih, iw, 4), "uint8")
    rgba[..., :3] = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    rgba[..., 3] = mask * int(255 * opacity)
    Image.fromarray(rgba, "RGBA").save(OUT / name, lossless=True, method=6)
    return name


MAGMA = [(0.0, (0, 0, 4)), (0.25, (81, 18, 124)), (0.5, (183, 55, 121)), (0.75, (252, 137, 97)), (1.0, (252, 253, 191))]


def coherence_png(folder, name):
    # Coherence is posted at 80 m, so the picture is half the base picture's size: nothing is lost
    files = sorted((PUBLIC / "sampling" / folder).glob("gunw-coherence_f*[0-9].tif"))
    ch, cw = ih // 2, iw // 2
    tf = from_origin(x0, y1, span_x / cw, span_y / ch)
    stack = np.stack([warp(f, (ch, cw), tf) for f in files])
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore", RuntimeWarning)
        c = np.nanmean(stack, 0) if len(files) > 1 else stack[0]
    ih_, iw_ = ch, cw
    ok = np.isfinite(c)
    v = np.clip(np.where(ok, c, 0), 0, 1)
    rgba = np.zeros((ih_, iw_, 4), "uint8")
    for k in range(3):
        rgba[..., k] = np.interp(v, [s for s, _ in MAGMA], [col[k] for _, col in MAGMA])
    rgba[..., 3] = ok * 235
    Image.fromarray(rgba, "RGBA").save(OUT / name, quality=82, method=6)
    return name, files


def ref(layer_id, **extra):
    l = L[layer_id]
    return {"name": l["name"], "attribution": l.get("attribution"), "limitations": l.get("limitations", []), **extra}


layers = [
    {"id": "unosat-extent", "file": vector_png("ref:unosat-extent", "unosat-extent.webp", "#e8590c", 0.8), "evidence": "reference", "color": "#e8590c", "on": True, **ref("ref:unosat-extent")},
    {"id": "unosat-detachment", "file": vector_png("ref:unosat-detachment", "unosat-detachment.webp", "#fa5252", 0.85), "evidence": "reference", "color": "#fa5252", "on": True, **ref("ref:unosat-detachment")},
    {"id": "unosat-lakes", "file": vector_png("ref:unosat-lakes", "unosat-lakes.webp", "#1c7ed6", 0.9), "evidence": "reference", "color": "#1c7ed6", "on": True, **ref("ref:unosat-lakes")},
    {"id": "unosat-roads", "file": vector_png("ref:unosat-roads", "unosat-roads.webp", "#ffd43b", 0.95, line_px=2), "evidence": "reference", "color": "#ffd43b", "on": False, **ref("ref:unosat-roads")},
    {"id": "rivers", "file": vector_png("ref:rivers", "rivers.webp", "#74c0fc", 0.8, line_px=1), "evidence": "reference", "color": "#74c0fc", "on": True, **ref("ref:rivers")},
]
obs = m["observability"]
views = m.get("observabilityViews") or {}
tracks = []
for folder, info, layer_id in [
    (f"rasuwa-2026-coherence-{obs['pair'][1].replace('-', '')}", obs, "rasuwa-2026:coherence-timeline"),
    (f"rasuwa-2026-coherence-t98-{views['t98']['pair'][1].replace('-', '')}", views.get("t98"), "rasuwa-2026:coherence-timeline-t98"),
]:
    if not info or not (PUBLIC / "sampling" / folder).exists():
        continue
    name, files = coherence_png(folder, f"coherence-t{info['track']}.webp")
    l = L[layer_id]
    layers.append({
        "id": f"coherence-t{info['track']}", "file": name, "evidence": "observed", "color": "#fc8961", "on": False, "group": "radar",
        "name": f"NISAR stability, Track {info['track']} ({info['orbit'].lower()}), {info['pair'][0]} to {info['pair'][1]}",
        "attribution": l.get("attribution"), "limitations": l.get("limitations", []), "maturity": l.get("productMaturity"),
        "granule": info.get("granule"), "short": f"Stability T{info['track']}", "kind": "coherence",
        "note": "Bright: the ground stayed the same between the two passes. Dark: it changed, or it is water or radar shadow. This pair spans the 26 August event, so a dark patch alone does not say what happened there.",
    })
    tracks.append({"track": info["track"], "orbit": info["orbit"], "look": info["look"], "losToSensorEastNorth": info["losToSensorEastNorth"],
                   "incidenceDeg5to95": info.get("incidenceDeg5to95"), "pair": info["pair"], "evidence": "derived"})

def ramp_png(path, name, stops, lo, hi, transform=None):
    """A picture from one sampling file (80 m), coloured on a fixed scale, at half the base picture's size."""
    ch, cw = ih // 2, iw // 2
    v = warp(path, (ch, cw), from_origin(x0, y1, span_x / cw, span_y / ch))
    if transform:
        with np.errstate(divide="ignore", invalid="ignore"):
            v = transform(v)
    ok = np.isfinite(v)
    t = np.clip((np.where(ok, v, lo) - lo) / (hi - lo), 0, 1)
    cols = [[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in stops]
    rgba = np.zeros((ch, cw, 4), "uint8")
    for k in range(3):
        rgba[..., k] = np.interp(t, np.linspace(0, 1, len(cols)), [c[k] for c in cols])
    rgba[..., 3] = ok * 235
    Image.fromarray(rgba, "RGBA").save(OUT / name, quality=80, method=6)
    return name


# NISAR GCOV snapshots and the change layers (prepare_nasa_rasuwa.py). Their evidence class follows the manifest's measurementClass.
BACK = "Bright: rough rock, debris and slopes facing the radar. Dark: smooth or wet ground, water, or radar shadow. One date on its own: it does not show change."
DIFF = "Orange: brighter on the second date. Blue: darker. White: little change. New debris, wet soil, snow and vegetation all change the radar return, so colour alone does not say what happened."
for lid, short, kind in [("gcov-0816:gcov-backscatter", "GCOV 16 Aug", "backscatter"), ("gcov-0823:gcov-backscatter", "GCOV 23 Aug", "backscatter"),
                         ("gcov-0828:gcov-backscatter", "GCOV 28 Aug", "backscatter"), ("gcov-0912:gcov-backscatter", "GCOV 12 Sep", "backscatter"),
                         ("gcov-0828:gcov-change", "NISAR change", "change"), ("rasuwa-2026:rtc-change-t019-0812", "S1 before", "change"),
                         ("rasuwa-2026:rtc-change-t019-0824", "S1 across", "change"), ("rasuwa-2026:rtc-change-t085-0816", "S1 across (asc)", "change")]:
    if lid not in L:
        continue
    l = L[lid]
    leg = l["legend"]
    fname = lid.split(":")[0].replace("rasuwa-2026", "opera") + "-" + lid.split(":")[1] + ".webp"
    fn = (lambda v: 10 * np.log10(v)) if l.get("displayDb") else None
    ramp_png(ROOT / "frontend/public" / l["sources"][0]["sampling"], fname, leg["stops"], leg["min"], leg["max"], fn)
    track = f"Track {l['track']}, {l['orbitDirection'].lower()}"
    when = l["acquisition"]["reference"] if not l["acquisition"]["secondary"] else f"{l['acquisition']['reference']} to {l['acquisition']['secondary']}"
    nm = (f"NISAR backscatter (HH), {track}, {when}" if kind == "backscatter" else l["name"] if l["mission"] == "OPERA" else f"NISAR backscatter change (HH), {track}, {when}")
    layers.append({"id": lid.replace(":", "-"), "file": fname, "evidence": "observed" if l["measurementClass"] == "measurement" else "derived", "color": leg["stops"][-1], "on": False, "group": "radar",
                   "name": nm, "short": short, "kind": kind, "note": BACK if kind == "backscatter" else DIFF, "legend": {"stops": leg["stops"], "min": leg["min"], "max": leg["max"], "unit": leg["unit"]},
                   "attribution": l["attribution"], "limitations": l["limitations"], "maturity": l.get("productMaturity")})

# Place names, in metres from the model's north-west corner
gj = json.loads((PUBLIC / "vectors/osm_places.geojson").read_text(encoding="utf-8"))
places = []
for f in gj["features"]:
    lon, lat = f["geometry"]["coordinates"][:2]
    px, py = fwd.transform(lon, lat)
    if f["properties"].get("label") and f["properties"].get("place") in ("town", "village", "city") and x0 <= px <= x0 + span_x and y1 - span_y <= py <= y1:
        places.append({"name": f["properties"]["label"], "xM": round(px - x0), "yM": round(y1 - py)})
# Keep one name where several sit within 4 km of each other, so the labels do not pile up
kept = []
for p in places:
    if all(np.hypot(p["xM"] - q["xM"], p["yM"] - q["yM"]) > 4000 for q in kept):
        kept.append(p)
places = kept[:24]

# Labels for the two UNOSAT features a reader looks for first, at their middle
markers = []
for layer_id, label in (("ref:unosat-detachment", "Landslide source (UNOSAT detachment zone)"), ("ref:unosat-lakes", "Barrier lakes (UNOSAT)")):
    gj = json.loads((ROOT / "frontend/public" / L[layer_id]["vector"]["url"]).read_text(encoding="utf-8"))
    from shapely.ops import unary_union
    c = unary_union([shape(f["geometry"]) for f in gj["features"]]).centroid
    px, py = fwd.transform(c.x, c.y)
    markers.append({"name": label, "xM": round(px - x0), "yM": round(y1 - py), "evidence": "reference"})

model = {
    "case": "rasuwa-2026", "name": "Rasuwa–Bhote Koshi–Trishuli corridor",
    "heights": "data/terrain/rasuwa-2026/heights.bin", "heightsType": "int16",
    "width": nx, "height": ny, "spacingM": GRID_M, "minM": float(z.min()), "maxM": float(z.max()),
    "crs": CRS, "originM": [float(x0), float(y1)], "drapeSize": [iw, ih], "base": "data/terrain/rasuwa-2026/base.jpg",
    "baseLayer": ref("context:terrain", evidence="reference"),
    "layers": [{**l, "file": f"data/terrain/rasuwa-2026/{l['file']}"} for l in layers],
    "tracks": tracks, "places": places, "markers": markers, "placesLayer": ref("ref:places", evidence="reference"),
}
(OUT / "model.json").write_text(json.dumps(model, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Grid {nx}x{ny} at {GRID_M} m, pictures {iw}x{ih}, heights {z.min():.0f} to {z.max():.0f} m, {len(layers)} layers, {len(places)} places")
