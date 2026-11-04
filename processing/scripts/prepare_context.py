"""Prepare the real, independent context: Copernicus DEM terrain, UNOSAT event layers, OSM geography and bookmarks.

usage: python prepare_context.py   (needs raw downloads in data/raw/context, see docs/DATA_ACQUISITION.md)
Needs no Earthdata login. Writes to frontend/public/data and data/metadata/prepared/context.json.
"""
import json
import pathlib
import re
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyogrio  # noqa: E402
import rasterio  # noqa: E402
import rasterio.coords  # noqa: E402
import rasterio.windows  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402
from rasterio.merge import merge  # noqa: E402
from shapely.geometry import box  # noqa: E402

from cascade_lens import export  # noqa: E402

CFG = json.loads((ROOT / "processing/configs/pipeline.json").read_text())
SRC = json.loads((ROOT / "processing/configs/context_sources.json").read_text())
BBOX = CFG["aoi_bbox"]
RAW, PUB, PREP = ROOT / "data/raw/context", ROOT / "frontend/public/data", ROOT / "data/metadata/prepared"
DEM_TILES = [f"Copernicus_DSM_COG_10_N{la}_00_E{lo}_00_DEM" for la in ("27", "28") for lo in ("084", "085")]
DEM_URL = "https://copernicus-dem-30m.s3.amazonaws.com/{0}/{0}.tif"
GDB = f"zip://{RAW}/unosat_extent/FL20260826NPL.gdb.zip!/FL20260826NPL.gdb"
UNOSAT_ATTR = "UNOSAT/UNITAR, event FL20260826NPL, CC BY-SA"
OSM_ATTR = "© OpenStreetMap contributors (ODbL), via HOT export on HDX"
NOT_VALIDATED = "UNOSAT records this layer as 'Not yet field validated'. Preliminary satellite-based mapping, not ground truth."


def terrain():
    srcs = [rasterio.open(DEM_URL.format(n)) for n in DEM_TILES]
    arr, tr = merge(srcs, bounds=BBOX, nodata=np.nan, dtype="float32", resampling=Resampling.nearest)
    crs_epsg = srcs[0].crs.to_epsg()
    for s in srcs:
        s.close()
    dem = arr[0]
    work = ROOT / "data/processed/context"
    tif = export.write_geotiff(work / "copdem_glo30.tif", dem, tr, crs_epsg, tags={"SOURCE": "Copernicus DEM GLO-30", "TILES": ",".join(DEM_TILES)})
    cog = export.to_cog(tif, PUB / "sampling/context/copdem_glo30.tif")
    validity = np.where(np.isfinite(dem), 1, 0).astype(np.uint8)
    vtif = export.write_geotiff(work / "copdem_glo30.validity.tif", validity, tr, crs_epsg, nodata=255)
    vcog = export.to_cog(vtif, PUB / "sampling/context/copdem_glo30_validity.tif")

    zmin, zmax = 7, 12
    grid, x0, y0 = export.warp_to_tile_grid(tif, zmax, Resampling.bilinear)
    res = 2 * export.ORIGIN / (256 * 2 ** zmax)
    gy, gx = np.gradient(np.nan_to_num(grid, nan=float(np.nanmedian(grid))), res * np.cos(np.radians(28)))
    az, alt = np.radians(315), np.radians(45)  # Conventional NW sun; hillshade is cosmetic, never measured
    slope, aspect = np.arctan(np.hypot(gx, gy)), np.arctan2(-gx, gy)
    shade = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
    rgba = export.colorize(grid, export.COLORMAPS["terrain"], 300, 6500)
    rgba[..., :3] = (rgba[..., :3] * (0.35 + 0.65 * shade[..., None])).astype(np.uint8)
    n = export.write_pyramid(rgba, x0, y0, zmax, zmin, PUB / "tiles/context/terrain", smooth=True)
    stats = export.statistics(dem, fixed=(300.0, 6500.0))
    bounds = list(rasterio.open(tif).bounds)
    print(f"terrain: {dem.shape}, {n} tiles, elevation {stats['min']:.0f}..{stats['max']:.0f} m")
    return {"id": "context:terrain", "groupId": None, "name": "Terrain elevation", "category": "terrain", "mission": "Copernicus DEM", "instrument": "TanDEM-X derived",
            "productType": "GLO-30", "measurementClass": "reference map", "measurementType": "elevation", "kind": "continuous", "units": "m", "unitsNote": "Metres above the EGM2008 geoid.",
            "acquisition": {"reference": "2011-2015 (source campaign)", "secondary": None}, "postingM": [30, 30], "crs": f"EPSG:{crs_epsg}", "status": "sampleable", "statusReason": None,
            "stats": stats, "qualityLayerIds": [], "orbitDirection": None, "track": None, "frames": [],
            "legend": {"type": "continuous", "stops": export.COLORMAPS["terrain"], "min": 300, "max": 6500, "unit": "m"},
            "sources": [{"frame": None, "granule": "Copernicus DEM GLO-30", "sourceFilename": ", ".join(f"{n}.tif" for n in DEM_TILES), "bounds": bounds, "validFraction": float(validity.mean()),
                         "sampling": cog.relative_to(PUB.parent).as_posix(), "validity": vcog.relative_to(PUB.parent).as_posix(),
                         "tiles": {"url": "data/tiles/context/terrain/{z}/{x}/{y}.png", "minzoom": zmin, "maxzoom": zmax, "count": n}}],
            "attribution": "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA",
            "limitations": ["A pre-event surface model: it does not show changes from the 2026 event."], "sourceGranules": [], "productMaturity": "Released product"}


def write_vector(gdf, name, keep=(), tol=None):
    g = gdf[[*keep, "geometry"]].copy()
    if tol:
        g["geometry"] = g.geometry.simplify(tol, preserve_topology=True)
    g = g[~g.geometry.is_empty & g.geometry.notna()].copy()
    g.geometry = g.geometry.force_2d()
    out = PUB / "vectors" / f"{name}.geojson"
    out.parent.mkdir(parents=True, exist_ok=True)
    g.to_file(out, driver="GeoJSON", COORDINATE_PRECISION=6)
    print(f"{name}: {len(g)} features, {out.stat().st_size / 1e6:.2f} MB")
    return out.relative_to(PUB.parent).as_posix(), [float(x) for x in g.total_bounds]


def vector_layer(id_, name, path, bounds, style, source, attribution, limits, dates, klass="reference map", mission="UNOSAT", page=None):
    return {"id": id_, "groupId": None, "name": name, "category": "reference", "mission": mission, "instrument": source, "productType": "Vector", "measurementClass": klass,
            "measurementType": "reference", "kind": "vector", "units": None, "acquisition": {"reference": dates, "secondary": None}, "crs": "EPSG:4326", "status": "prepared", "statusReason": None,
            "qualityLayerIds": [], "orbitDirection": None, "track": None, "frames": [], "sources": [], "vector": {"url": path, **style, "bounds": bounds}, "attribution": attribution,
            "limitations": limits, "sourceGranules": [], "productMaturity": "Preliminary" if mission == "UNOSAT" else "Community-maintained", "page": page}


def unosat():
    def read(layer):
        return gpd.read_file(GDB, layer=layer).to_crs(4326)

    flood = read("UNOSAT_Multisensor_20260826_20260828_FloodExtent")
    extent = read("UNOSAT_Multisensors_20260826_20260828_AnalysisExtent")
    lakes = read("UNOSAT_Cartosat3_20260828_BarrierLakes")
    zone = read("UNOSAT_Landsat9_20260826_DetachmentZone")
    roads = read("UNOSAT_Multisensor_20260826_20260828_AffectedRoads")
    bld = read("UNOSAT_Multisensor_20260826_20260828_AffectedBuildings")
    roads["geometry"] = roads.geometry.intersection(extent.union_all())  # Source geometry has stray vertices far outside Nepal
    km2 = lambda g: round(float(g.to_crs(32645).area.sum()) / 1e6, 2)  # noqa: E731
    page = SRC["unosat_extent"]["page"]
    fp, fb = write_vector(flood, "unosat_mudflow_extent", tol=0.00005)
    ep, eb = write_vector(extent, "unosat_analysis_extent")
    lp, lb = write_vector(lakes, "unosat_barrier_lakes", tol=0.00002)
    zp, zb = write_vector(zone, "unosat_detachment_zone")
    rp, rb = write_vector(roads, "unosat_affected_roads", tol=0.00005)
    bp, bb = write_vector(bld, "unosat_affected_buildings")
    fill = lambda c, o=0.45: {"type": "fill", "color": c, "opacity": o}  # noqa: E731
    layers = [
        vector_layer("ref:unosat-extent", f"UNOSAT mudflow/rockflow extent ({km2(flood)} km²)", fp, fb, fill("#e8590c"), "Multi-sensor optical/satellite analysis", UNOSAT_ATTR,
                     [NOT_VALIDATED, "Independent of NISAR. Area computed here in UTM 45N from the polygon, because the source's Area_ha attribute duplicates Area_m2."], "26–28 August 2026", page=page),
        vector_layer("ref:unosat-analysis", "UNOSAT analysis extent", ep, eb, {"type": "line", "color": "#f5f5f5", "opacity": 0.8, "dash": True}, "Analysis boundary", UNOSAT_ATTR,
                     ["Absence of mapped impact outside this boundary says nothing: it was not analysed."], "26–28 August 2026", page=page),
        vector_layer("ref:unosat-lakes", f"UNOSAT barrier lakes ({km2(lakes)} km²)", lp, lb, fill("#1c7ed6", 0.75), "Cartosat-3", UNOSAT_ATTR, [NOT_VALIDATED], "28 August 2026", page=page),
        vector_layer("ref:unosat-detachment", f"UNOSAT detachment zone ({km2(zone)} km²)", zp, zb, fill("#fa5252", 0.55), "Landsat-9", UNOSAT_ATTR,
                     [NOT_VALIDATED, "Source inconsistency: layer name says 26 August 2026 but its SensorDate attribute says 26 September 2026. Treat the date as unresolved."], "26 August 2026 (see limitations)", page=page),
        vector_layer("ref:unosat-roads", "UNOSAT affected roads", rp, rb, {"type": "line", "color": "#ffd43b", "opacity": 0.95}, "Multi-sensor analysis", UNOSAT_ATTR,
                     [NOT_VALIDATED, "Clipped to the UNOSAT analysis extent because the source contains stray vertices outside Nepal."], "26–28 August 2026", page=page),
        vector_layer("ref:unosat-buildings", f"UNOSAT affected structures ({len(bld):,} points)", bp, bb, {"type": "circle", "color": "#ffa94d", "opacity": 0.9, "radius": 2}, "Multi-sensor analysis", UNOSAT_ATTR,
                     [NOT_VALIDATED], "26–28 August 2026", page=page),
    ]
    return layers, zone, lakes, extent


def osm():
    aoi = box(*BBOX)
    water = gpd.read_file(RAW / "osm_waterways/hot_flood_npl_waterways_osm.geojson")
    water = water[water.geometry.geom_type.isin(["LineString", "MultiLineString"]) & water["waterway"].isin(["river", "stream"])]
    water = water[water.intersects(aoi)].copy()
    places = gpd.read_file(RAW / "osm_places/hot_flood_npl_populated_places_osm.geojson")
    places = places[places.geometry.geom_type == "Point"].copy()
    z = zipfile.ZipFile(RAW / "osm_roads/hot_flood_npl_roads_osm_gpkg.zip")
    name = next(n for n in z.namelist() if n.endswith(".gpkg"))
    roads = gpd.read_file(f"zip://{RAW.as_posix()}/osm_roads/hot_flood_npl_roads_osm_gpkg.zip!/{name}")
    roads = roads[roads.intersects(aoi)].copy()
    keep = [c for c in ("highway",) if c in roads]
    major = roads[roads["highway"].isin(["trunk", "primary", "secondary", "tertiary", "unclassified", "track"])] if keep else roads
    water["label"] = water["name_en"].fillna(water["name"])
    places["label"] = places["name_en"].fillna(places["name"])
    places = places[places["label"].fillna("").map(lambda s: bool(re.fullmatch(r"[\x00-\x7f]+", s)))].copy()
    wp, wb = write_vector(water, "osm_rivers", keep=["label", "waterway"], tol=0.00005)
    rp, rb = write_vector(major, "osm_roads", keep=keep, tol=0.00005)
    pp, pb = write_vector(places, "osm_places", keep=["label", "place"])
    src = SRC["osm_waterways"]["page"]
    notes = ["Community mapping exported after the event; features may predate or postdate the disaster."]
    layers = [vector_layer("ref:rivers", "Rivers (OSM)", wp, wb, {"type": "line", "color": "#74c0fc", "opacity": 0.85}, "OpenStreetMap", OSM_ATTR, notes, "HDX export, 2026", "contextual", "OpenStreetMap", src),
              vector_layer("ref:roads", "Roads (OSM)", rp, rb, {"type": "line", "color": "#adb5bd", "opacity": 0.7}, "OpenStreetMap", OSM_ATTR, notes, "HDX export, 2026", "contextual", "OpenStreetMap", src),
              vector_layer("ref:places", "Settlements (OSM)", pp, pb, {"type": "label"}, "OpenStreetMap", OSM_ATTR, notes, "HDX export, 2026", "contextual", "OpenStreetMap", src)]
    return layers, water, places


def damage_proxy():
    """The file is a coloured RGBA picture with no underlying values, so it is map-only: `renderable`, never `sampleable`."""
    src = SRC["eos_dpm"]
    z = next((RAW / "eos_dpm").glob("*.zip"))
    name = next(n for n in zipfile.ZipFile(z).namelist() if n.lower().endswith(".tif"))
    tif = pathlib.Path(zipfile.ZipFile(z).extract(name, ROOT / "data/interim"))
    with rasterio.open(tif) as d:
        win = rasterio.windows.from_bounds(*BBOX, transform=d.transform).round_offsets().round_lengths()
        bands, tr, crs = d.read(window=win), d.window_transform(win), d.crs
    zmin, zmax = 8, 12
    rgba, x0, y0 = export.warp_rgba(bands, tr, crs, BBOX, zmax)
    n = export.write_pyramid(rgba, x0, y0, zmax, zmin, PUB / "tiles/context/eos_dpm")
    coloured = float((bands[3] > 0).mean())
    print(f"eos_dpm: {n} tiles, {coloured:.2%} of the envelope has coloured pixels")
    return {"id": "ref:eos-dpm", "groupId": None, "name": "Sentinel-1 damage proxy map (EOS-RS)", "category": "reference", "mission": "Sentinel-1", "instrument": "C-band SAR", "productType": "Damage proxy map v0.9",
            "measurementClass": "derived", "measurementType": "reference", "kind": "continuous", "units": None, "acquisition": {"reference": "Before 5 May–16 Aug 2026; during 28 Aug 2026", "secondary": None},
            "orbitDirection": None, "track": None, "frames": [], "postingM": [30, 30], "crs": "EPSG:4326", "qualityLayerIds": [], "status": "renderable", "statusReason": None,
            "legend": {"type": "continuous", "stops": ["#ffff00", "#ff0000"], "lowLabel": "Less change", "highLabel": "More change", "unit": None},
            "sources": [{"frame": None, "granule": name[:-4], "sourceFilename": name, "bounds": [float(x) for x in rasterio.coords.BoundingBox(*BBOX)],
                         "tiles": {"url": "data/tiles/context/eos_dpm/{z}/{x}/{y}.png", "minzoom": zmin, "maxzoom": zmax, "count": n}}],
            "attribution": "Earth Observatory of Singapore - Remote Sensing Lab (EOS-RS). Contains modified Copernicus Sentinel data (2026), processed by ESA. CC BY", "page": src["page"],
            "limitations": ["Not NISAR. Sentinel-1 is a separate C-band mission.", "A coloured picture with no measurement values, so the inspector cannot sample it.",
                            "EOS-RS calls it preliminary guidance. It may be less reliable over vegetated or mountainous areas, and scattered pixels there may be false positives.",
                            "A lack of coloured pixels does not necessarily mean an absence of damage."],
            "sourceGranules": [], "productMaturity": "Preliminary v0.9"}


def change_screening():
    area_zip = next((RAW / "impact_area").glob("*.zip"))
    poly_zip = next((RAW / "impact_screening").glob("*.zip"))
    read = lambda z: gpd.read_file(f"zip://{z.as_posix()}!/{next(n for n in zipfile.ZipFile(z).namelist() if n.endswith('.shp'))}")  # noqa: E731
    change, area = read(poly_zip), read(area_zip).to_crs(4326)
    ha = round(float(change.to_crs(32645).area.sum()) / 1e4)
    change = change.to_crs(4326)
    src = SRC["impact_screening"]
    attr = "IMPACT Initiatives / REACH, using Copernicus Sentinel-1 data. CC BY"
    limits = ["Not NISAR. Sentinel-1 is a separate C-band mission.", "Measures radar backscatter change, not structural damage. Debris, water, moisture, vegetation or clearance can all produce the signal, and damaged structures may show none.",
              "Only assessed around pre-event built areas, so it says nothing about open ground."]
    cp, cb = write_vector(change, "impact_s1_change", tol=0.00002)
    ap, ab = write_vector(area, "impact_analyzed_area", tol=0.0002)
    return [vector_layer("ref:impact-change", f"Sentinel-1 change screening ({ha} ha, REACH)", cp, cb, {"type": "fill", "color": "#e599f7", "opacity": 0.8}, "Sentinel-1 backscatter change", attr, limits,
                         "Baseline Aug 2025–Aug 2026; post-event 28 Aug 2026", "derived", "Sentinel-1", src["page"]),
            vector_layer("ref:impact-area", "REACH analysed area", ap, ab, {"type": "line", "color": "#e599f7", "opacity": 0.6, "dash": True}, "Analysis boundary", attr,
                         ["Absence of mapped change outside this boundary says nothing: it was not analysed."], "2 September 2026", "reference map", "Sentinel-1", src["page"])]


def districts():
    z = next((RAW / "admin_boundaries").glob("*.zip"))
    root = zipfile.ZipFile(z).namelist()[0].split("/")[0]
    g = gpd.read_file(f"zip://{z.as_posix()}!/{root}", layer="npl_admin2").to_crs(4326)
    g = g[g.intersects(box(*BBOX))].copy()
    g["geometry"] = g.geometry.boundary.clip_by_rect(*BBOX)
    p, b = write_vector(g, "districts", tol=0.0002)
    src = SRC["admin_boundaries"]
    return vector_layer("ref:districts", "District boundaries (COD-AB)", p, b, {"type": "line", "color": "#c0b6f2", "opacity": 0.7, "dash": True}, "Survey Department of Nepal", "Survey Department of Nepal and UN RCO, via OCHA COD-AB. CC BY-IGO",
                        ["Administrative reference only."], "Valid from March 2024", "contextual", "COD-AB", src["page"])


def pad(b, d):
    return [round(float(b[0]) - d, 4), round(float(b[1]) - d, 4), round(float(b[2]) + d, 4), round(float(b[3]) + d, 4)]


def bookmarks(zone, lakes, water, places):
    """All bounds derive from named source features. They are navigation frames, not event delineations."""
    src = pd.concat([zone.geometry, lakes.geometry])
    bhote = water[water["label"].fillna("").eq("Bhote Koshi")]
    tri = water[water["label"].fillna("").str.contains("Tris?h?uli", regex=True)]
    bet = float(places[places["label"] == "Betrawati"].geometry.y.iloc[0])
    tri_b = tri.geometry.clip_by_rect(BBOX[0], BBOX[1], BBOX[2], bet)
    tri_b = tri_b[~tri_b.is_empty]

    def place(label):
        p = places[places["label"] == label].geometry.iloc[0]
        return {"lng": round(float(p.x), 5), "lat": round(float(p.y), 5), "label": label}

    centre = zone.to_crs(32645).geometry.iloc[0].representative_point()
    zone_pt = gpd.GeoSeries([centre], crs=32645).to_crs(4326).iloc[0]
    return [{"id": "source", "name": "Mountain source area", "bounds": pad(list(src.total_bounds), 0.03),
             "anchor": {"lng": round(float(zone_pt.x), 5), "lat": round(float(zone_pt.y), 5), "label": "UNOSAT detachment zone"},
             "basis": "UNOSAT detachment zone and barrier lakes polygons, padded 0.03°. Approximate navigation frame."},
            {"id": "bhote-koshi", "name": "Bhote Koshi corridor", "bounds": pad(list(bhote.total_bounds), 0.02), "anchor": place("Shyaphru Bensi"),
             "basis": "OSM waterways named Bhote Koshi, padded 0.02°. Approximate navigation frame."},
            {"id": "trishuli", "name": "Trishuli downstream corridor", "bounds": pad(list(tri_b.total_bounds), 0.02), "anchor": place("Betrawati"),
             "basis": "OSM Trishuli waterways south of Betrawati, inside the search envelope, padded 0.02°. Approximate navigation frame."}]


def main():
    PREP.mkdir(parents=True, exist_ok=True)
    t = terrain()
    u, zone, lakes, extent = unosat()
    o, water, places = osm()
    bm = bookmarks(zone, lakes, water, places)
    layers = [t, *u, damage_proxy(), *change_screening(), *o, districts()]
    (PREP / "context.json").write_text(json.dumps({"layers": layers, "bookmarks": bm}, indent=1), encoding="utf-8")
    for b in bm:
        print(b["id"], b["bounds"])


if __name__ == "__main__":
    main()
