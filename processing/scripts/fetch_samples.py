"""Download NASA's public NISAR sample granules: 2008 ALOS-derived scenes over California, in the real product format.

They test this code against real files with no login. They are NOT Rasuwa data and must never appear in the app as such.
usage: python fetch_samples.py   (about 540 MB; cached files are skipped; used by tests/integration/test_real_format.py)
"""
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
for u in json.loads((ROOT / "processing/configs/sample_products.json").read_text()):
    product = u.split("/NISAR-SAMPLE-DATA/")[1].split("/")[0]
    target = ROOT / "data/raw/samples" / product / u.rsplit("/", 1)[1]
    if target.exists() and target.stat().st_size:
        print("cached", target.name[-40:])
        continue
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(u, timeout=500) as r, open(target, "wb") as out:
        while chunk := r.read(1 << 20):
            out.write(chunk)
    print(target.name[-40:], target.stat().st_size, "bytes")
