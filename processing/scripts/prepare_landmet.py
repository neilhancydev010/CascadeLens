"""Turn a LANDMET L3 file into the app's second case study.

usage: python prepare_landmet.py path/to/landmet_L3_20071231_v1.nc
Writes frontend/public/data/manifests/landmet.json, plus COGs and tiles. Refuses to write a broken manifest.
"""
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import landmet, manifest  # noqa: E402

source = pathlib.Path(sys.argv[1])
public = ROOT / "frontend/public/data"
for rel in ("tiles/landmet", "sampling/landmet"):
    shutil.rmtree(public / rel, ignore_errors=True)
m = landmet.prepare(source, public, ROOT / "data/processed/landmet", ROOT / "data/qa")
errors = manifest.validate(m, ROOT / "frontend/public")
if errors:
    sys.exit("Manifest not written:\n" + "\n".join(errors))
out = public / "manifests/landmet.json"
out.write_text(json.dumps(m, indent=1), encoding="utf-8")
counts = {}
for l in m["layers"]:
    counts[l["status"]] = counts.get(l["status"], 0) + 1
print(f"{len(m['layers'])} layers {counts}. Daily skin temperature peak: {m['qa']['diurnalPeakLocalHour']}h local solar time")
