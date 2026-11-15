"""Search ASF for NISAR products over the Rasuwa envelope and write data/metadata/catalogue.json.

usage: python discover_products.py [--start 2026-08-01] [--end 2026-10-01] [--out ../../data/metadata/catalogue.json]
No Earthdata credentials needed: catalogue search is public. Downloading is not.
"""
import argparse
import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from cascade_lens import discovery  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--start", default="2026-08-01T00:00:00Z")
ap.add_argument("--end", default="2026-10-01T00:00:00Z")
ap.add_argument("--out", default=str(pathlib.Path(__file__).resolve().parents[2] / "data/metadata/catalogue.json"))
a = ap.parse_args()

g = discovery.search(a.start, a.end)
discovery.dump(g, a.out)
rows = collections.Counter((x.product, x.direction[0], x.track, x.frame, x.ref_date, x.sec_date) for x in g)
for k in sorted(rows, key=lambda k: (k[0], k[4] or "", k[2], k[3])):
    print(*k)
print(f"{len(g)} granules -> {a.out}")
