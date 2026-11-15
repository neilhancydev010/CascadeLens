"""SOFTWARE TEST ONLY. Runs the NISAR pipeline on non-Rasuwa data to prove the browser path, served apart from the real app.

    python tests/integration/build_fixture.py            invented HDF5 with known pixels, used by frontend/e2e
    python tests/integration/build_fixture.py --sample   NASA's public 2008 California sample files, in the real format
    npm run dev:fixture                                  from frontend/, port 5199

Output goes to tests/fixtures/public, which is gitignored and never part of a build. The manifest sets fixture=true, so the
app shows a permanent banner saying what the data is.
"""
import json
import pathlib
import shutil
import sys

from pyproj import Transformer

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "processing/src"), str(ROOT / "tests/processing")]
import conftest as fx  # noqa: E402
from cascade_lens import discovery, manifest, pipeline, previews  # noqa: E402

SAMPLE = "--sample" in sys.argv
OUT = ROOT / "tests/fixtures"
shutil.rmtree(OUT, ignore_errors=True)
work = OUT / "work"
work.mkdir(parents=True)
(OUT / "public/data").mkdir(parents=True)
for rel in ("tiles/context", "sampling/context", "vectors"):
    shutil.copytree(ROOT / "frontend/public/data" / rel, OUT / "public/data" / rel)
cfg = json.loads((ROOT / "processing/configs/pipeline.json").read_text())
cfg["fixture"] = True


def sample_inputs():
    root = ROOT / "data/raw/samples"
    h5 = {p: next(f for f in (root / p).glob("*.h5")) for p in ("GUNW", "GOFF", "GCOV")}
    quad = previews.parse_kml_quad(next((root / "GUNW").glob("*.kml")).read_text(encoding="utf-8"))
    lons, lats = zip(*quad)
    cfg["aoi_bbox"] = [min(lons), min(lats), max(lons), max(lats)]
    cfg["crid"] = "D00404"
    cfg["fixture_label"] = "SAMPLE FILE TEST. NASA's public 2008 ALOS-derived scene over California, used to test the software. This is not Rasuwa data."
    cfg["pairs"] = [{"id": "pair-a", "label": "12 Oct–27 Nov 2008", "role": "Software test only", "direction": "ASCENDING", "track": 30, "frames": [19],
                     "ref_date": "2008-10-12", "sec_date": "2008-11-27", "products": ["GUNW", "GOFF"]}]
    cfg["snapshots"] = [{"id": "gcov-0828", "label": "12 Oct 2008", "direction": "ASCENDING", "track": 30, "frames": [19], "date": "2008-10-12"}]
    ring = [[*p] for p in quad] + [[*quad[0]]]
    groups = {"GUNW": "pair-a", "GOFF": "pair-a", "GCOV": "gcov-0828"}
    return [({**discovery.parse_file_id(f.stem), "file_id": f.stem, "group": groups[p], "size_mb": None, "url": None, "geometry": {"type": "Polygon", "coordinates": [ring]}}, f) for p, f in h5.items()]


def synthetic_inputs():
    # Place the invented grid over the Bhote Koshi corridor so masks and sampling can be checked at known spots
    fx.X0, fx.Y0 = (float(v) for v in Transformer.from_crs(4326, fx.EPSG, always_xy=True).transform(85.33, 28.25))
    fx.N, fx.POST = 500, 80.0
    cfg["pairs"] = [{**cfg["pairs"][0], "frames": [74]}]
    cfg["snapshots"] = [{**cfg["snapshots"][0], "frames": [74]}]
    out = []
    for product, make, group in (("GUNW", fx.make_gunw, "pair-a"), ("GOFF", fx.make_goff, "pair-a"), ("GCOV", fx.make_gcov, "gcov-0828")):
        p = work / f"{product}.h5"
        make(p)
        g = {**fx.granule(product, group=group), "file_id": f"SYNTHETIC_{product}_F74_P05023_TEST", "geometry": None}
        out.append((g, p))
    return out


meta = work / "data/metadata"
(meta / "granules").mkdir(parents=True)
(meta / "prepared").mkdir()
inputs = sample_inputs() if SAMPLE else synthetic_inputs()
for g, p in inputs:
    state, recs = pipeline.process_granule(g, p, cfg, work / "processed", work / "qa")
    print(g["product"], state["status"], state.get("reason"), {k: round(v, 3) for k, v in state.get("validFraction", {}).items()})
    (meta / "granules" / f"{g['file_id']}.json").write_text(json.dumps(state, default=str))
    for r in recs:
        pipeline.finalize_layer(r["measurement"], [r], cfg, OUT / "public/data", meta / "prepared")
(meta / "catalogue.json").write_text(json.dumps([g for g, _ in inputs]))
shutil.copy(ROOT / "data/metadata/prepared/context.json", meta / "prepared/context.json")
m = manifest.build(work, cfg)
(OUT / "public/data/manifests").mkdir(parents=True)
(OUT / "public/data/manifests/manifest.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
print({l["id"]: l["status"] for l in m["layers"] if l["mission"] == "NISAR"})
print("fixture manifest errors:", manifest.validate(m, OUT / "public"))
