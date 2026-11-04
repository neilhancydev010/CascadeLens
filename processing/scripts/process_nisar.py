"""Process every downloaded, configured NISAR granule. Run generate_manifest.py afterwards to publish the results to the app.

usage: python process_nisar.py   (safe to rerun; reads data/raw/nisar, never modifies it)
"""
import collections
import json
import logging
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import pipeline  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("process_nisar")

cfg = json.loads((ROOT / "processing/configs/pipeline.json").read_text())
cat = json.loads((ROOT / "data/metadata/catalogue.json").read_text())
raw, meta = ROOT / "data/raw", ROOT / "data/metadata"
(meta / "granules").mkdir(parents=True, exist_ok=True)
layers = collections.defaultdict(list)
for g in pipeline.select_granules(cat, cfg):
    path = pipeline.granule_path(raw, g)
    if not path.exists():
        log.info("not downloaded: %s", g["file_id"])
        continue
    try:
        state, records = pipeline.process_granule(g, path, cfg, ROOT / "data/processed", ROOT / "data/qa")
    except Exception as e:  # One unreadable granule must not stop the others, and must be visible as invalid
        log.exception("failed: %s", g["file_id"])
        state, records = {"file_id": g["file_id"], "status": "invalid", "reason": f"{type(e).__name__}: {e}"}, []
    (meta / "granules" / f"{g['file_id']}.json").write_text(json.dumps(state, indent=1), encoding="utf-8")
    log.info("%s -> %s %s", g["file_id"], state["status"], state.get("reason") or "")
    for r in records:
        layers[r["group"], r["measurement"]].append(r)
for (_, mid), rs in layers.items():
    pipeline.finalize_layer(mid, rs, cfg, ROOT / "frontend/public/data", meta / "prepared")
    log.info("prepared %s", mid)
