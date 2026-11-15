"""Turn the NASA cut-outs from extract_nasa_rasuwa.py into map layers for the Rasuwa case, and record them in the manifest.

usage: python prepare_nasa_rasuwa.py   (after extract_nasa_rasuwa.py; then run prepare_rasuwa_3d.py)
Reads data/processed/nasa/ and writes, under frontend/public/data:
  sampling/context/nasadem.tif and tiles/context/terrain/      NASADEM replaces the Copernicus DEM as the Rasuwa terrain layer
  sampling|tiles/gcov-<mmdd>/gcov-backscatter                  one NISAR GCOV HH snapshot per date (Observed)
  sampling|tiles/gcov-0828/gcov-change                         Track 48 HH change, 16 to 28 August (Derived)
  sampling|tiles/rasuwa-2026/rtc-change-*                      OPERA RTC-S1 VV change for 12-day Sentinel-1 pairs (Derived)
It patches manifests/manifest.json in place (layers and snapshot groups) and data/metadata/prepared/context.json (terrain),
so the map, the inspector and a later generate_manifest.py --keep-merged agree. Sampling files are posted at 80 m and tiles
stop at zoom 11 to keep the web payload small. Nothing here is a classification, a forecast or a warning.
"""
import json
import pathlib
import shutil
import sys
from datetime import date

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.shutil import copy as rio_copy
from rasterio.transform import Affine

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import export  # noqa: E402

N = ROOT / "data/processed/nasa"
PUB = ROOT / "frontend/public/data"
WORK = N / "_work"
WORK.mkdir(parents=True, exist_ok=True)
MAN = PUB / "manifests/manifest.json"
CTX = ROOT / "data/metadata/prepared/context.json"
NISAR_ATTR = "NASA/JPL-Caltech/ISRO, NISAR; distributed by ASF DAAC"
OPERA_ATTR = "NASA/JPL OPERA RTC-S1 (from Copernicus Sentinel-1 data, ESA); distributed by ASF DAAC"
NASADEM_ATTR = "NASA JPL, NASADEM Merged DEM Global 1 arc second V001 (doi:10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001); distributed by NASA LP DAAC"
EVENT = "2026-08-26"
GREY = {"type": "continuous", "stops": export.COLORMAPS["grey"], "min": -22, "max": 2, "unit": "dB",
        "lowLabel": "Dark: smooth or wet ground, water, shadow", "highLabel": "Bright: rough rock, slopes facing the radar"}
CHANGE = {"type": "continuous", "stops": export.COLORMAPS["diverging"], "min": -6, "max": 6, "unit": "dB",
          "lowLabel": "Darker on the second date", "highLabel": "Brighter on the second date"}
SAMPLE_K = 2  # 40 m cut-outs, averaged 2 x 2 into 80 m sampling files
ZMIN, ZMAX = 8, 11


def rel(p):
    return p.relative_to(PUB.parent).as_posix()


def read(name):
    with rasterio.open(N / name) as s:
        return s.read(1), s.transform, s.crs.to_epsg()


def cog(arr, tf, epsg, dst, tags=None):
    """A cloud-optimised float32 copy with a float predictor: much smaller than the default for smooth fields."""
    tmp = WORK / (dst.name + ".tmp.tif")
    with rasterio.open(tmp, "w", driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1, dtype="float32", crs=f"EPSG:{epsg}",
                       transform=tf, nodata=np.nan) as d:
        d.write(arr.astype("float32"), 1)
        if tags:
            d.update_tags(**{k: str(v) for k, v in tags.items()})
    dst.parent.mkdir(parents=True, exist_ok=True)
    rio_copy(str(tmp), str(dst), driver="COG", compress="DEFLATE", predictor=3, blocksize=256, overview_resampling="nearest")
    tmp.unlink()
    return dst


def coarsen(a, tf, k=SAMPLE_K):
    h, w = (a.shape[0] // k) * k, (a.shape[1] // k) * k
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore", RuntimeWarning)
        out = np.nanmean(a[:h, :w].reshape(h // k, k, w // k, k), axis=(1, 3))
    return out, tf * Affine.scale(k)


def tiles(arr, tf, epsg, folder, stops, lo, hi):
    """Display tiles from a 40 m grid: averaged onto the zoom-11 grid, then coloured."""
    tmp = WORK / "tile_src.tif"
    with rasterio.open(tmp, "w", driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1, dtype="float32", crs=f"EPSG:{epsg}",
                       transform=tf, nodata=np.nan) as d:
        d.write(arr.astype("float32"), 1)
    grid, x0, y0 = export.warp_to_tile_grid(tmp, ZMAX, Resampling.average)
    out = PUB / "tiles" / folder
    if out.exists():
        shutil.rmtree(out)
    n = export.write_pyramid(export.colorize(grid, stops, lo, hi), x0, y0, ZMAX, ZMIN, out)
    return {"url": f"data/tiles/{folder}/{{z}}/{{x}}/{{y}}.png", "minzoom": ZMIN, "maxzoom": ZMAX, "count": n}


def bounds4326(arr, tf, epsg):
    from rasterio.warp import transform_bounds
    rows, cols = np.where(np.isfinite(arr))
    if not rows.size:
        return None
    x0, y1 = tf * (cols.min(), rows.min())
    x1, y0 = tf * (cols.max() + 1, rows.max() + 1)
    return [round(v, 6) for v in transform_bounds(f"EPSG:{epsg}", "EPSG:4326", x0, y0, x1, y1)]


def db(a):
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(a)


def day(d):
    return date.fromisoformat(d).strftime("%-d %B %Y")


# ---------------------------------------------------------------- terrain
def terrain():
    dem, tf, epsg = read("nasadem.tif")
    c = cog(dem, tf, epsg, PUB / "sampling/context/nasadem.tif", {"SOURCE": "NASADEM_HGT v001"})
    validity = np.where(np.isfinite(dem), 1, 0).astype(np.uint8)
    vtmp = export.write_geotiff(WORK / "nasadem.validity.tif", validity, tf, epsg, nodata=255)
    vc = export.to_cog(vtmp, PUB / "sampling/context/nasadem_validity.tif")
    zmin, zmax = 7, 12
    grid, x0, y0 = export.warp_to_tile_grid(N / "nasadem.tif", zmax, Resampling.bilinear)
    res = 2 * export.ORIGIN / (256 * 2 ** zmax)
    gy, gx = np.gradient(np.nan_to_num(grid, nan=float(np.nanmedian(grid))), res * np.cos(np.radians(28)))
    az, alt = np.radians(315), np.radians(45)  # Conventional NW sun; hillshade is cosmetic, never measured
    slope, aspect = np.arctan(np.hypot(gx, gy)), np.arctan2(-gx, gy)
    shade = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
    rgba = export.colorize(grid, export.COLORMAPS["terrain"], 300, 6500)
    rgba[..., :3] = (rgba[..., :3] * (0.35 + 0.65 * shade[..., None])).astype(np.uint8)
    out = PUB / "tiles/context/terrain"
    shutil.rmtree(out, ignore_errors=True)
    n = export.write_pyramid(rgba, x0, y0, zmax, zmin, out, smooth=True)
    stats = export.statistics(dem, fixed=(300.0, 6500.0))
    tiles_ = sorted(p.name for p in pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").glob("NASADEM_HGT_*.zip")) or ["NASADEM_HGT_n27e084.zip", "NASADEM_HGT_n27e085.zip", "NASADEM_HGT_n28e084.zip", "NASADEM_HGT_n28e085.zip"]
    print(f"terrain: NASADEM {dem.shape}, {n} tiles, {stats['min']:.0f}..{stats['max']:.0f} m, COG {c.stat().st_size / 1e6:.1f} MB")
    return {"id": "context:terrain", "groupId": None, "name": "Terrain elevation", "category": "terrain", "mission": "NASADEM", "instrument": "SRTM C-band radar (Shuttle Radar Topography Mission)",
            "productType": "NASADEM_HGT v001", "measurementClass": "reference map", "measurementType": "elevation", "kind": "continuous", "units": "m", "unitsNote": "Metres above the EGM96 geoid.",
            "acquisition": {"reference": "2000-02 (SRTM flight, reprocessed 2020)", "secondary": None}, "postingM": [30, 30], "crs": f"EPSG:{epsg}", "status": "sampleable", "statusReason": None,
            "stats": stats, "qualityLayerIds": [], "orbitDirection": None, "track": None, "frames": [],
            "legend": {"type": "continuous", "stops": export.COLORMAPS["terrain"], "min": 300, "max": 6500, "unit": "m"},
            "sources": [{"frame": None, "granule": "NASADEM_HGT v001", "sourceFilename": ", ".join(tiles_), "bounds": [round(v, 6) for v in rasterio.open(N / "nasadem.tif").bounds],
                         "validFraction": float(validity.mean()), "sampling": rel(c), "validity": rel(vc),
                         "tiles": {"url": "data/tiles/context/terrain/{z}/{x}/{y}.png", "minzoom": zmin, "maxzoom": zmax, "count": n}}],
            "attribution": NASADEM_ATTR,
            "limitations": ["A pre-event surface model from the February 2000 SRTM flight: it does not show changes from the 2026 event, or the 26 years before it.",
                            "Gaps in steep terrain and radar shadow were filled from other elevation models during NASA's reprocessing, so heights on the steepest walls are less certain."],
            "sourceGranules": [], "productMaturity": "Released product (v001)"}


# ---------------------------------------------------------------- NISAR GCOV
def gcov():
    metas = [json.loads(p.read_text()) for p in sorted(N.glob("gcov_*_hh.json"))]
    groups, layers, grids = [], [], {}
    for mt in metas:
        stem = f"gcov_{mt['date'].replace('-', '')}_t{mt['track']:03d}_hh"
        a, tf, epsg = read(f"{stem}.tif")
        gid = f"gcov-{mt['date'][5:7]}{mt['date'][8:10]}"
        grids[gid] = (a, tf, epsg, mt)
        s, stf = coarsen(a, tf)
        c = cog(s, stf, epsg, PUB / f"sampling/{gid}/gcov-backscatter_f{mt['frame']:03d}.tif", {"SOURCE": mt["sourceFilename"], "DATASET": mt["dataset"], "AVERAGED": "linear gamma-0, 80 m"})
        t = tiles(db(a), tf, epsg, f"{gid}/gcov-backscatter/f{mt['frame']:03d}", GREY["stops"], GREY["min"], GREY["max"])
        when = "Pre-event" if mt["date"] < EVENT else "Post-event"
        mode = f"{mt['modeBandwidthMHz']} MHz radar mode, {mt['sourcePostingM']:.0f} m posting in the file"
        groups.append({"id": gid, "kind": "snapshot", "label": day(mt["date"]), "role": f"{when} radar backscatter snapshot", "direction": mt["orbit"], "track": mt["track"],
                       "frames": [mt["frame"]], "reference": mt["date"], "secondary": None, "products": ["GCOV"], "available": True, "statusReason": None})
        limits = ["A single-date snapshot, not a damage or flood classification.",
                  f"Covers {mt['validFraction'] * 100:.0f}% of the case area: only frame {mt['frame']} was downloaded, and the product's own mask removes samples that were not fully focused.",
                  f"{mode}; averaged here to 40 m for the map and 80 m for the inspector, in linear power.",
                  "Provisional data."]
        if mt["track"] == 149:
            limits.append("Track 149 is a different descending orbit from Track 48: do not difference it against Track 48 dates.")
        if mt["track"] == 98:
            limits.append("Ascending pass: it views slopes from the opposite side to Tracks 48 and 149. Do not difference it against descending dates.")
        layers.append({"id": f"{gid}:gcov-backscatter", "groupId": gid, "name": "Gamma-0 backscatter (HH)", "category": "gcov", "mission": "NISAR", "instrument": "L-SAR",
                       "productType": "GCOV", "measurementClass": "measurement", "measurementType": "gcov-backscatter", "kind": "continuous", "units": "1",
                       "unitsNote": "Displayed in dB (10·log10) from the linear gamma-0 term; the inspector reports both.",
                       "acquisition": {"reference": mt["date"], "secondary": None}, "orbitDirection": mt["orbit"], "track": mt["track"], "frames": [mt["frame"]],
                       "postingM": [80.0, 80.0], "crs": f"EPSG:{epsg}", "qualityLayerIds": [], "status": "sampleable", "statusReason": None,
                       "sources": [{"frame": mt["frame"], "granule": mt["granule"], "sourceFilename": mt["sourceFilename"], "sourceDataset": mt["dataset"], "bounds": bounds4326(a, tf, epsg),
                                    "validFraction": mt["validFraction"], "sampling": rel(c), "tiles": t}],
                       "stats": export.statistics(db(s), fixed=(GREY["min"], GREY["max"])), "polarization": ["HH"], "displayDb": True, "displayRelative": False, "goffLayer": None,
                       "legend": GREY, "productMaturity": f"Provisional ({mt['release']})", "sourceGranules": [mt["granule"]], "attribution": NISAR_ATTR, "limitations": limits,
                       "processingHistory": {"processedAt": date.today().isoformat(), "parameters": {"script": "extract_nasa_rasuwa.py + prepare_nasa_rasuwa.py", "average": "mean of valid linear samples per 40 m cell", "doi": mt["doi"], "urgentObservation": mt["urgent"]}}})
        print(f"{gid}: T{mt['track']} f{mt['frame']} {mt['date']}, {t['count']} tiles, sampling {c.stat().st_size / 1e6:.1f} MB")

    # Track 48 change across the event: same orbit track and frame, so the viewing geometry matches
    a0, tf, epsg, m0 = grids["gcov-0816"]
    a1, _, _, m1 = grids["gcov-0828"]
    d = db(a1) - db(a0)
    s0, stf = coarsen(a0, tf)
    s1, _ = coarsen(a1, tf)
    sd = np.round(db(s1) - db(s0), 2)  # 0.01 dB is far below the speckle, and the file compresses much better
    c = cog(sd, stf, epsg, PUB / "sampling/gcov-0828/gcov-change_f074.tif", {"SOURCE": f"{m0['sourceFilename']}, {m1['sourceFilename']}", "METHOD": "10log10(28 Aug) - 10log10(16 Aug), HH"})
    t = tiles(d, tf, epsg, "gcov-0828/gcov-change/f074", CHANGE["stops"], CHANGE["min"], CHANGE["max"])
    layers.append({"id": "gcov-0828:gcov-change", "groupId": "gcov-0828", "name": "Backscatter change, 16 to 28 August (HH)", "category": "gcov", "mission": "NISAR", "instrument": "L-SAR",
                   "productType": "Derived here", "measurementClass": "derived", "measurementType": "gcov-change", "kind": "continuous", "units": "dB",
                   "unitsNote": "28 August minus 16 August, in dB, from 80 m averages of the linear gamma-0 terms.",
                   "acquisition": {"reference": m0["date"], "secondary": m1["date"]}, "orbitDirection": "DESCENDING", "track": 48, "frames": [74],
                   "postingM": [80.0, 80.0], "crs": f"EPSG:{epsg}", "qualityLayerIds": [], "status": "sampleable", "statusReason": None,
                   "sources": [{"frame": 74, "granule": f"{m0['granule']} and {m1['granule']}", "sourceFilename": f"{m0['sourceFilename']}, {m1['sourceFilename']}", "sourceDataset": m0["dataset"],
                                "bounds": bounds4326(d, tf, epsg), "validFraction": float(np.isfinite(d).mean()), "sampling": rel(c), "tiles": t}],
                   "stats": export.statistics(sd, fixed=(CHANGE["min"], CHANGE["max"])), "polarization": ["HH"], "displayDb": False, "displayRelative": False, "goffLayer": None,
                   "legend": CHANGE, "productMaturity": "Derived from provisional data (P05023)", "sourceGranules": [m0["granule"], m1["granule"]], "attribution": f"Derived by CascadeLens from {NISAR_ATTR}",
                   "explanation": {"what": "How much brighter or darker the radar saw each spot on 28 August than on 16 August, from the same NISAR track.",
                                   "measures": "The difference of two gamma-0 HH backscatter values, in decibels.",
                                   "inspect": "Look for strong change inside the mapped mudflow compared with the ground around it.",
                                   "establishes": "Change in how the surface returned the radar. Wet soil, snow, vegetation and new debris all change it, so it does not establish the cause."},
                   "limitations": ["Derived from two dates; the 26 August event falls between them, and so does 12 days of monsoon weather.",
                                   f"The two files use different radar modes ({m0['modeBandwidthMHz']} and {m1['modeBandwidthMHz']} MHz, {m0['sourcePostingM']:.0f} and {m1['sourcePostingM']:.0f} m), averaged to the same 40 m grid first.",
                                   f"Only frame 74 was downloaded: {np.isfinite(d).mean() * 100:.0f}% of the case area has both dates.", "Provisional data."]})
    return groups, layers


# ---------------------------------------------------------------- OPERA RTC-S1
RTC = [("019", "DESCENDING", "2026-08-12", "2026-08-24", "before"), ("019", "DESCENDING", "2026-08-24", "2026-09-05", "across"), ("085", "ASCENDING", "2026-08-16", "2026-08-28", "across")]


def opera(src_names):
    layers = []
    for rel_orbit, orbit, d0, d1, when in RTC:
        a0, tf, epsg = read(f"opera_{d0.replace('-', '')}_t{rel_orbit}_vv.tif")
        a1, _, _ = read(f"opera_{d1.replace('-', '')}_t{rel_orbit}_vv.tif")
        d = db(a1) - db(a0)
        s0, stf = coarsen(a0, tf)
        s1, _ = coarsen(a1, tf)
        sd = np.round(db(s1) - db(s0), 2)  # 0.01 dB is far below the speckle, and the file compresses much better
        lid = f"rtc-change-t{rel_orbit}-{d0[5:].replace('-', '')}"
        c = cog(sd, stf, epsg, PUB / f"sampling/rasuwa-2026/{lid}.tif", {"METHOD": f"10log10({d1}) - 10log10({d0}), VV"})
        t = tiles(d, tf, epsg, f"rasuwa-2026/{lid}", CHANGE["stops"], CHANGE["min"], CHANGE["max"])
        files = [n for n in src_names if f"_T{rel_orbit}-" in n and (d0.replace("-", "") in n or d1.replace("-", "") in n) and n.endswith("_VV.tif")]
        label = {"before": "before the event (control)", "across": "across the event"}[when]
        layers.append({"id": f"rasuwa-2026:{lid}", "groupId": None, "name": f"Sentinel-1 backscatter change {label}, {day(d0)[:-5]} to {day(d1)[:-5]} (OPERA, track {int(rel_orbit)})",
                       "category": "gridded", "mission": "OPERA", "instrument": "Sentinel-1 C-SAR, via NASA JPL OPERA RTC-S1", "productType": "Derived here",
                       "measurementClass": "derived", "measurementType": "rtc-change", "kind": "continuous", "units": "dB",
                       "unitsNote": f"{day(d1)} minus {day(d0)}, VV, in dB, from 80 m averages of the linear gamma-0 terms.",
                       "acquisition": {"reference": d0, "secondary": d1}, "orbitDirection": orbit, "track": int(rel_orbit), "frames": [],
                       "postingM": [80.0, 80.0], "crs": f"EPSG:{epsg}", "qualityLayerIds": [], "status": "sampleable", "statusReason": None,
                       "sources": [{"frame": None, "granule": f"OPERA_L2_RTC-S1 T{rel_orbit}, {len(files)} bursts", "sourceFilename": ", ".join(files), "sourceDataset": "VV gamma-0 (with the product's layover/shadow mask)",
                                    "bounds": bounds4326(d, tf, epsg), "validFraction": float(np.isfinite(d).mean()), "sampling": rel(c), "tiles": t}],
                       "stats": export.statistics(sd, fixed=(CHANGE["min"], CHANGE["max"])), "legend": CHANGE, "displayDb": False,
                       "productMaturity": "Derived from OPERA RTC-S1 v1.0 (provisional validation)", "sourceGranules": files, "attribution": f"Derived by CascadeLens from {OPERA_ATTR}",
                       "explanation": {"what": f"How much brighter or darker Sentinel-1 saw each spot on {day(d1)} than on {day(d0)}, from NASA's OPERA terrain-corrected images of one orbit track.",
                                       "measures": "The difference of two gamma-0 VV backscatter values, in decibels.",
                                       "inspect": "Compare the pair across the event with the 12-day pair before it, inside and outside the mapped mudflow.",
                                       "establishes": "Change in how the surface returned the radar. It does not establish the cause, and it is a different mission from NISAR."},
                       "limitations": ["Sentinel-1 is an ESA mission; NASA's OPERA project made these terrain-corrected images from it. Not a NISAR result.",
                                       ("Both dates are before 26 August: this is the control for ordinary 12-day change." if when == "before" else "The 26 August event falls between the two dates, and so does 12 days of monsoon weather."),
                                       "Layover and shadow pixels flagged by OPERA are left out.", "C-band reacts to soil moisture and vegetation more than NISAR's L-band."]})
        print(f"{lid}: {t['count']} tiles, sampling {c.stat().st_size / 1e6:.1f} MB")
    return layers


def change_check():
    """Share of pixels whose backscatter changed by more than 3 dB, inside the UNOSAT extent and in a 1 km ring around it,
    for each pair. Written to data/qa so the claims register can cite it. A summary, not a detection."""
    import geopandas as gpd
    from rasterio.features import rasterize
    _, tf, _ = read("gcov_20260816_t048_hh.tif")
    shape_ = read("gcov_20260816_t048_hh.tif")[0].shape
    ext = gpd.read_file(PUB / "vectors/unosat_mudflow_extent.geojson").to_crs(32645).union_all()
    zones = {"unosatExtent": ext, "ring1km": ext.buffer(1000).difference(ext),
             "detachmentZone": gpd.read_file(PUB / "vectors/unosat_detachment_zone.geojson").to_crs(32645).union_all()}
    masks = {k: rasterize([(g, 1)], out_shape=shape_, transform=tf, dtype="uint8").astype(bool) for k, g in zones.items()}
    pairs = [("NISAR GCOV HH, Track 48", "gcov_20260816_t048_hh.tif", "gcov_20260828_t048_hh.tif")]
    pairs += [(f"OPERA RTC-S1 VV, track {int(r)}", f"opera_{a.replace('-', '')}_t{r}_vv.tif", f"opera_{b.replace('-', '')}_t{r}_vv.tif") for r, _, a, b, _ in RTC]
    pairs.append(("OPERA RTC-S1 VV, track 85", "opera_20260828_t085_vv.tif", "opera_20260909_t085_vv.tif"))
    out = []
    for name, a, b in pairs:
        d = db(read(b)[0]) - db(read(a)[0])
        row = {"pair": name, "first": a, "second": b, "zones": {}}
        for k, m in masks.items():
            v = d[m & np.isfinite(d)]
            row["zones"][k] = {"pixels40m": int(m.sum()), "validShare": round(float(v.size / m.sum()), 3),
                               "medianDb": round(float(np.median(v)), 2) if v.size else None, "shareOver3Db": round(float(np.mean(np.abs(v) > 3)), 3) if v.size else None}
        out.append(row)
        z = row["zones"]
        print(f"{name} {a[-19:-11]}->{b[-19:-11]}: >3 dB {z['unosatExtent']['shareOver3Db']} in extent ({z['unosatExtent']['validShare']} valid), {z['ring1km']['shareOver3Db']} in ring")
    qa = ROOT / "data/qa/rasuwa-2026-backscatter-change.json"
    qa.write_text(json.dumps({"method": "10log10(second) - 10log10(first) on 40 m means of linear gamma-0; |change| > 3 dB counted; NaN (masked, outside the frame) left out",
                              "eventDate": EVENT, "pairs": out}, indent=1) + "\n")


def write_json(path, obj):
    raw = path.read_bytes()
    text = json.dumps(obj, indent=1, ensure_ascii=raw.isascii()) + ("\n" if raw.rstrip(b"\r\n") != raw else "")
    path.write_bytes((text.replace("\n", "\r\n") if b"\r\n" in raw else text).encode("utf-8"))


if __name__ == "__main__":
    src = pathlib.Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
    names = sorted(p.name for p in src.glob("OPERA_L2_RTC-S1_*")) if src else []
    m = json.loads(MAN.read_text(encoding="utf-8"))
    terr = terrain()
    groups, glayers = gcov()
    olayers = opera(names)
    new = {l["id"]: l for l in [terr, *glayers, *olayers]}
    layers = [new.pop(l["id"], l) for l in m["layers"]]
    # New layers go after their family: GCOV after the last GCOV layer, OPERA after the last gridded layer
    for l in new.values():
        idx = max((i for i, x in enumerate(layers) if x.get("category") == l["category"]), default=len(layers) - 1)
        layers.insert(idx + 1, l)
    m["layers"] = layers
    gids = {g["id"]: g for g in groups}
    m["groups"] = [gids.pop(g["id"], g) for g in m["groups"]] + list(gids.values())
    m["groups"].sort(key=lambda g: (g["kind"] != "pair", g["reference"]))
    write_json(MAN, m)
    ctx = json.loads(CTX.read_text(encoding="utf-8"))
    ctx["layers"] = [terr if l["id"] == "context:terrain" else l for l in ctx["layers"]]
    write_json(CTX, ctx)
    print(f"manifest: {len(m['layers'])} layers, {len(m['groups'])} groups")
    change_check()
