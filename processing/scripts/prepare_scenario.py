"""Add a dam-failure scenario to a glacial lake case that prepare_lake.py has already built.

usage: python prepare_scenario.py processing/configs/lake/tsho-rolpa.json FOLDER_WITH_COPERNICUS_DEM
Reads frontend/public/data/manifests/<id>.json and the lake edge, writes the scenario into the same manifest.
A scenario is "what if the dam breached", with ranges. It is not a prediction that it will, and not a warning.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import export, manifest, scenario  # noqa: E402

cfg = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
dems = sorted(pathlib.Path(sys.argv[2]).glob("Copernicus_DSM*.tif"))
if not dems:
    sys.exit(f"No Copernicus_DSM*.tif in {sys.argv[2]}")
public = ROOT / "frontend/public/data"
case = cfg["id"]
mpath = public / f"manifests/{case}.json"
m = json.loads(mpath.read_text(encoding="utf-8"))
lake = json.loads((public / f"vectors/{case}-lake.geojson").read_text(encoding="utf-8"))
area = round(sum(p["areaKm2"] for p in m["lake"]["series"]) / len(m["lake"]["series"]), 3)
work = ROOT / "data/processed" / case
work.mkdir(parents=True, exist_ok=True)
sc = scenario.run(dems[0], lake, area, (cfg["lake"]["lng"], cfg["lake"]["lat"]), public, case, work)
shade = sc.pop("_shade")
sc["dem"] = dems[0].name
m["lake"]["scenario"] = sc
common = {"groupId": None, "category": "reference", "mission": "Copernicus DEM", "instrument": None, "productType": "Scenario", "measurementClass": "derived",
          "measurementType": "reference", "kind": "vector", "units": None, "acquisition": {"reference": "scenario", "secondary": None}, "crs": "EPSG:4326",
          "status": "prepared", "statusReason": None, "qualityLayerIds": [], "orbitDirection": None, "track": None, "frames": [], "sources": [],
          "attribution": "Scenario by CascadeLens from Copernicus DEM GLO-30 and the NISAR lake area", "sourceGranules": [], "productMaturity": "Scenario", "page": None}
bounds = m["caseStudy"]["searchEnvelope"]
layers = [{**common, "id": "ref:scenario-route", "name": "River route below the dam", "vector": {"url": sc["routeVector"], "type": "line", "color": "#7fd4ff", "opacity": 0.95, "bounds": bounds},
           "limitations": ["Traced on a 60 m terrain model with depressions filled. It follows the valley floor, not the exact river channel."]},
          {**common, "id": "ref:scenario-extent", "name": "Flooded area if a 20 m breach (scenario)", "vector": {"url": sc["extentVector"], "type": "fill", "color": "#2f8cff", "opacity": 0.35, "bounds": bounds},
           "limitations": ["Scenario only: the widest case (highest peak flow, smoothest channel) for a 20 m breach, from 60 m terrain cross-sections every 500 m.",
                           "The peak is not reduced downstream, so the area is larger than a real flood of this size would cover far from the lake."]}]
if shade:
    zmin, zmax = 8, 12
    warped, tx, ty = export.warp_to_tile_grid(shade, zmax, resampling=__import__("rasterio").enums.Resampling.bilinear)
    folder = public / f"tiles/{case}/hillshade"
    n = export.write_pyramid(export.colorize(warped, ["#0b0f11", "#56636a"], 0.0, 1.0), tx, ty, zmax, zmin, folder, smooth=True)
    layers.append({**common, "id": "context:hillshade", "name": "Terrain shading (Copernicus DEM)", "category": "terrain", "measurementType": "dem-hillshade", "kind": "continuous",
                   "mission": "Copernicus DEM", "productType": "GLO-30", "vector": None, "status": "renderable",
                   "sources": [{"frame": None, "granule": sc["dem"], "sourceFilename": sc["dem"], "bounds": sc["bounds"],
                                "tiles": {"url": f"data/tiles/{case}/hillshade/{{z}}/{{x}}/{{y}}.png", "minzoom": zmin, "maxzoom": zmax, "count": n}}],
                   "legend": {"type": "continuous", "stops": ["#0b0f11", "#56636a"], "min": 0, "max": 1, "unit": None},
                   "explanation": {"what": "Shaded relief of the valleys below the lake.", "measures": "Nothing: light and shadow from the terrain heights.",
                                   "inspect": "Use it to follow the river route.", "establishes": "Landscape context only."},
                   "attribution": "Copernicus DEM GLO-30: © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA",
                   "limitations": ["Shading only, from 60 m averaged heights."]})
m["layers"] = [l for l in m["layers"] if l["id"] not in {x["id"] for x in layers}] + layers
errors = manifest.validate(m, ROOT / "frontend/public")
if errors:
    sys.exit("Manifest not written:\n" + "\n".join(errors))
mpath.write_text(json.dumps(m, indent=1), encoding="utf-8")
print(f"Route {sc['routeKm']} km to {sc['routeEnd']}")
for s in sc["scenarios"]:
    a = s["arrival"]
    pick = [x for x in a if x[0] in (5.0, 10.0, 20.0, 30.0, 50.0)] or a[::20]
    print(f"breach {s['breachM']} m: {s['volumeM3'] / 1e6:.0f} million m3, peak {s['peakRange'][0]:,} to {s['peakRange'][1]:,} m3/s, arrival (km, fastest min, slowest min): {pick}")
