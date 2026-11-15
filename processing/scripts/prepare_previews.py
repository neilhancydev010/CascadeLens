"""Emergency mode: tile NISAR browse PNGs fetched with `download_products.py --qa-only`. Run generate_manifest.py afterwards.

usage: python prepare_previews.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import pipeline, previews  # noqa: E402

cfg = json.loads((ROOT / "processing/configs/pipeline.json").read_text())
cat = json.loads((ROOT / "data/metadata/catalogue.json").read_text())
layers = previews.prepare(pipeline.select_granules(cat, cfg), ROOT / "data/raw/nisar/qa", ROOT / "frontend/public/data", cfg)
out = ROOT / "data/metadata/prepared/previews.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(layers, indent=1), encoding="utf-8")
print(f"{len(layers)} preview layers -> {out}")
