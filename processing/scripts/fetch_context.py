"""Download the public reference datasets listed in processing/configs/context_sources.json into data/raw/context.

usage: python fetch_context.py   (no login needed; cached files are skipped)
"""
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
for key, src in json.loads((ROOT / "processing/configs/context_sources.json").read_text()).items():
    folder = ROOT / "data/raw/context" / key
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / src["url"].rsplit("/", 1)[1]
    if target.exists() and target.stat().st_size:
        print(key, "cached")
        continue
    req = urllib.request.Request(src["url"], headers={"User-Agent": "cascade-lens/0.1"})
    with urllib.request.urlopen(req, timeout=280) as r, open(target, "wb") as out:
        while chunk := r.read(1 << 20):
            out.write(chunk)
    print(key, target.stat().st_size, "bytes")
