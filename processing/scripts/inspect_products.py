"""Inspect downloaded NISAR HDF5 granules. JSON and Markdown reports go to data/qa/.

usage: python inspect_products.py [file.h5 ...]   (default: every granule in data/raw/nisar)
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import nisar  # noqa: E402

files = [pathlib.Path(p) for p in sys.argv[1:]] or sorted((ROOT / "data/raw/nisar").glob("*.h5"))
if not files:
    sys.exit("No granules found in data/raw/nisar. Run download_products.py first.")
qa = ROOT / "data/qa"
qa.mkdir(parents=True, exist_ok=True)
for f in files:
    product = f.name.split("_")[3]
    r = nisar.inspect(f, product)
    i = r["identification"]
    (qa / f"{f.stem}.inspection.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    lines = [f"# {r['file']}", "", *(f"- **{k}**: {v}" for k, v in i.items() if k != "boundingPolygon"),
             f"- **polarizations**: {r['polarizations']}", f"- **datasets**: {r['dataset_count']} in {r['group_count']} groups",
             f"- **mask present**: {r['mask_present']}", "", "| Dataset | Shape | Type | Units | Fill | EPSG | Posting (m) |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {p} | {d['shape']} | {d['dtype']} | {d['attrs'].get('units')} | {d['attrs'].get('_FillValue')} | {d['epsg']} | {d['posting_m']} |" for p, d in r["datasets"].items()]
    lines += ["", f"Missing: {r['missing'] or 'none'}", f"Unit mismatches: {r['unit_mismatch'] or 'none'}"]
    (qa / f"{f.stem}.inspection.md").write_text("\n".join(lines), encoding="utf-8")
    print(f.name, "missing:", len(r["missing"]), "unit mismatches:", len(r["unit_mismatch"]))
