"""Turn NISAR GCOV files over a glacial lake into a case study with a lake-size time series.

usage: python prepare_lake.py processing/configs/lake/tsho-rolpa.json FOLDER_WITH_GCOV_H5_FILES [MORE_FOLDERS...]
A Copernicus DEM tile (Copernicus_DSM_*.tif) in the same folder adds the 3D model.
GUNW and GOFF pair files in any of the folders (data/raw/nisar is always searched) add the dam and glacier movement test.
Writes frontend/public/data/manifests/<id>.json, plus COGs, tiles, compare images and the lake edge. Refuses to write a broken manifest.
"""
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import lake, manifest  # noqa: E402

cfg = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
files = sorted(p for p in pathlib.Path(sys.argv[2]).glob("NISAR_L2_*GCOV*.h5") if f"_{cfg['track']:03d}_" in p.name and f"_{cfg['frame']:03d}_" in p.name)
if len(files) < 2:
    sys.exit(f"Need at least 2 GCOV files for track {cfg['track']} frame {cfg['frame']} in {sys.argv[2]}, found {len(files)}")
public = ROOT / "frontend/public/data"
case = cfg["id"]
for rel in (f"tiles/{case}", f"sampling/{case}", f"compare/{case}", f"terrain/{case}"):
    shutil.rmtree(public / rel, ignore_errors=True)
dems = sorted(pathlib.Path(sys.argv[2]).glob("Copernicus_DSM*.tif"))
pairs = [pathlib.Path(f) for f in sys.argv[2:]] + [ROOT / "data/raw/nisar"]
m = lake.prepare(cfg, files, public, ROOT / "data/processed" / case, ROOT / "data/qa", dems[0] if dems else None, pairs)
print("3D model:", f"heights from {dems[0].name}" if dems else "no Copernicus DEM tile in the folder, so no 3D model")
errors = manifest.validate(m, ROOT / "frontend/public")
if errors:
    sys.exit("Manifest not written:\n" + "\n".join(errors))
(public / f"manifests/{case}.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
print(f"{len(files)} dates. Change first to last: {m['lake']['changeKm2']:+.3f} km2, method range about ±{m['lake']['methodHalfRangeKm2']:.3f} km2")
