"""Regenerate frontend/public/data/manifests/manifest.json from the files actually present. Refuses to write a broken manifest."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import manifest  # noqa: E402

cfg = json.loads((ROOT / "processing/configs/pipeline.json").read_text())
m = manifest.build(ROOT, cfg)
errors = manifest.validate(m, ROOT / "frontend/public")
if errors:
    sys.exit("Manifest not written:\n" + "\n".join(errors))
out = ROOT / "frontend/public/data/manifests/manifest.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(m, indent=1), encoding="utf-8")
counts = {}
for l in m["layers"]:
    counts[l["status"]] = counts.get(l["status"], 0) + 1
print(f"{len(m['layers'])} layers {counts}, {len(m['granules'])} granules -> {out}")
