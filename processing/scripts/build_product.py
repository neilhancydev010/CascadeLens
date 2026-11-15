"""Assemble the finished product: CascadeLens.zip, ready to unzip and double-click.

usage: python build_product.py [output-folder]   (run `npm run build` in frontend/ first)
Contains the built app, the launcher, and the source without raw data or rebuildable folders. Refuses to package anything credential-shaped.
"""
import pathlib
import re
import shutil
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT.parent
SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", ".pytest_cache", ".venv", "test-results", "fixtures"}
SKIP_PATHS = ("data/raw", "data/interim", "data/processed", "frontend/public/data", "product")
TOKEN = re.compile(rb"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")
TEXT = (".py", ".ts", ".tsx", ".json", ".md", ".txt", ".css", ".html", ".mjs", ".js", ".toml", ".csv", ".geojson", ".bat", ".example")

dist = ROOT / "frontend/dist"
if not (dist / "index.html").exists():
    sys.exit("No build found. Run `npm run build` in frontend/ first.")
entries = []
for p in sorted((ROOT / "product").iterdir()):
    entries.append((p, f"CascadeLens/{p.name}"))
for p in sorted(dist.rglob("*")):
    if p.is_file():
        entries.append((p, f"CascadeLens/app/{p.relative_to(dist).as_posix()}"))
for p in sorted(ROOT.rglob("*")):
    rel = p.relative_to(ROOT).as_posix()
    if p.is_file() and not set(rel.split("/")) & SKIP_DIRS and not rel.startswith(SKIP_PATHS):
        entries.append((p, f"CascadeLens/source/{rel}"))
for p, name in entries:
    if p.suffix.lower() in TEXT and TOKEN.search(p.read_bytes()):
        sys.exit(f"Refusing to package credential-shaped content: {name}")
OUT.mkdir(parents=True, exist_ok=True)
target = OUT / "CascadeLens.zip"
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for p, name in entries:
        z.write(p, name)
with zipfile.ZipFile(target) as z:
    if z.testzip():
        sys.exit("Zip failed its integrity check")
print(f"{len(entries)} files, {target.stat().st_size / 1e6:.1f} MB -> {target}")
