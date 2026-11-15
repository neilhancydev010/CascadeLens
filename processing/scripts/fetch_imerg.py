"""Download GPM IMERG V07 daily rainfall for a box, one small OPeNDAP subset per day (audit P2, datasets B1 and C5).

    python fetch_imerg.py [--run late|final] [--start 2016-06-01] [--end 2026-10-31] [--bbox 84.0 27.5 86.5 29.5] [--workers 6]

Needs an Earthdata Login token for gpm1.gesdisc.eosdis.nasa.gov. In a cloud session the network proxy adds it; elsewhere
put it in the environment as EARTHDATA_TOKEN. Each day is saved as the subset GES DISC returns (NetCDF-4: precipitation,
precipitation_cnt, randomError, lat, lon, time) under data/raw/rainfall/gesdisc/<collection>/<year>/, with its original
file name plus ".subset.nc4". Days already on disk are skipped, so the command can be rerun after a dropped connection.
The server often answers 502 for a moment, so every request is retried with backoff. Then run prepare_rainfall.py.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import math
import os
import pathlib
import re
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[2]
HOST = "https://gpm1.gesdisc.eosdis.nasa.gov"
COLLECTIONS = {"late": "GPM_3IMERGDL.07", "final": "GPM_3IMERGDF.07"}
VARS = ("precipitation", "precipitation_cnt", "randomError")


def get(url: str, tries: int = 20, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url)
    if os.environ.get("EARTHDATA_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['EARTHDATA_TOKEN']}")
    wait = 1.0  # the 502s come and go at random, not under load, so retries stay short
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError) as e:
            code = getattr(e, "code", None)
            if code in (401, 403, 404) or i == tries - 1:
                raise
            time.sleep(wait)
            wait = min(wait * 1.3, 8)
    raise RuntimeError("unreachable")


def month_files(collection: str, year: int, month: int) -> dict[str, str]:
    """{YYYYMMDD: file name} from the month's directory listing (the version suffix changes over time: V07B, V07C)."""
    html = get(f"{HOST}/data/GPM_L3/{collection}/{year}/{month:02d}/").decode("utf-8", "replace")
    names = set(re.findall(r'href="(3B-DAY[^"]*?\.(\d{8})-S000000-E235959\.V07[A-Z]\.nc4)"', html))
    return {d: n for n, d in names}


def index_range(lo: float, hi: float, origin: float, n: int) -> tuple[int, int]:
    """First and last 0.1 degree cell whose centre lies inside [lo, hi]."""
    first = math.ceil((lo - origin) / 0.1 - 0.5)
    last = math.floor((hi - origin) / 0.1 - 0.5)
    return max(first, 0), min(last, n - 1)


def subset_url(collection: str, name: str, bbox: list[float]) -> str:
    y, m = name.split(".")[4][:4], name.split(".")[4][4:6]
    x0, x1 = index_range(bbox[0], bbox[2], -180.0, 3600)
    y0, y1 = index_range(bbox[1], bbox[3], -90.0, 1800)
    ce = ",".join([f"{v}[0:0][{x0}:{x1}][{y0}:{y1}]" for v in VARS] + [f"lon[{x0}:{x1}]", f"lat[{y0}:{y1}]", "time[0:0]"])
    return f"{HOST}/opendap/GPM_L3/{collection}/{y}/{m}/{name}.nc4?{ce}"


def fetch_day(collection: str, name: str, bbox: list[float], out: pathlib.Path) -> str:
    dest = out / name.split(".")[4][:4] / f"{name}.subset.nc4"
    if dest.exists() and dest.stat().st_size > 0:
        return "kept"
    data = get(subset_url(collection, name, bbox))
    if not data.startswith(b"\x89HDF"):
        raise RuntimeError(f"{name}: the server did not return NetCDF-4 ({data[:60]!r})")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(dest)  # a dropped connection never leaves a file that looks complete
    return "new"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", choices=sorted(COLLECTIONS), default="late")
    ap.add_argument("--start", default="2016-06-01")
    ap.add_argument("--end", default="2026-10-31")
    ap.add_argument("--bbox", nargs=4, type=float, default=[84.0, 27.5, 86.5, 29.5], metavar=("W", "S", "E", "N"))
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)
    collection = COLLECTIONS[a.run]
    out = ROOT / "data/raw/rainfall/gesdisc" / collection
    start, end = date.fromisoformat(a.start), date.fromisoformat(a.end)
    months = sorted({(d.year, d.month) for d in (start + timedelta(i) for i in range((end - start).days + 1))})
    with cf.ThreadPoolExecutor(a.workers) as ex:  # one directory listing per month
        files = {k: v for listing in ex.map(lambda ym: month_files(collection, *ym), months) for k, v in listing.items()}
    names, missing = [], []
    for d in (start + timedelta(i) for i in range((end - start).days + 1)):
        (names.append(files[d.strftime("%Y%m%d")]) if d.strftime("%Y%m%d") in files else missing.append(d.isoformat()))
    print(f"{collection}: {len(names)} days listed, {len(missing)} not on the server{': ' + ', '.join(missing[:10]) if missing else ''}", flush=True)
    counts: dict[str, int] = {}
    failed = []
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(fetch_day, collection, n, a.bbox, out): n for n in names}
        for i, f in enumerate(cf.as_completed(futs), 1):
            try:
                counts[f.result()] = counts.get(f.result(), 0) + 1
            except Exception as e:  # noqa: BLE001 - report every failed day, then fail
                failed.append(f"{futs[f]}: {e}")
            if i % 200 == 0:
                print(f"{i}/{len(names)} {counts}", flush=True)
    print(f"done {counts}, failed {len(failed)}", flush=True)
    if failed:
        print("\n".join(failed[:20]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
