"""Regenerate frontend/public/data/manifests/manifest.json from the files actually present. Refuses to write a broken manifest.

    python generate_manifest.py [--keep-merged]

--keep-merged keeps what merge_observability.py folded into the current manifest (observability, its further views, the
control series, hazards, access and their layers), so adding one pair does not mean rerunning every analysis. Without it,
rerun merge_observability.py on the fragments afterwards. The file keeps its line endings."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import manifest  # noqa: E402

cfg = json.loads((ROOT / "processing/configs/pipeline.json").read_text())
m = manifest.build(ROOT, cfg)
out = ROOT / "frontend/public/data/manifests/manifest.json"
raw = out.read_bytes() if out.exists() else b""
if "--keep-merged" in sys.argv and raw:
    m = manifest.keep_merged(m, json.loads(raw.decode("utf-8")))
errors = manifest.validate(m, ROOT / "frontend/public")
if errors:
    sys.exit("Manifest not written:\n" + "\n".join(errors))
out.parent.mkdir(parents=True, exist_ok=True)
text = json.dumps(m, indent=1) + ("\n" if raw.endswith(b"\n") else "")
out.write_bytes((text.replace("\n", "\r\n") if b"\r\n" in raw else text).encode("utf-8"))
counts = {}
for l in m["layers"]:
    counts[l["status"]] = counts.get(l["status"], 0) + 1
print(f"{len(m['layers'])} layers {counts}, {len(m['granules'])} granules -> {out}")
