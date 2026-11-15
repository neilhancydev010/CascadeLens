"""Download every landslide incident in Nepal's BIPAD disaster information portal (NDRRMA), for dataset C1 (audit P2).

    python fetch_bipad.py [--since 2011-01-01]

Reads the public API (https://bipadportal.gov.np/api/v1/incident/, hazard 17 = landslide) page by page, with each record's
loss block expanded, and writes the records unchanged to data/raw/hazard/bipad/incidents_landslide.json, plus the ward
table (centroids) the records point to, so prepare_bipad_inventory.py can tell a site point from a ward centroid.
Then run prepare_bipad_inventory.py.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
API = "https://bipadportal.gov.np/api/v1"
OUT = ROOT / "data/raw/hazard/bipad"
LANDSLIDE = 17


def get(url: str, tries: int = 8) -> dict:
    wait = 2.0
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=120) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
            if i == tries - 1:
                raise
            time.sleep(wait)
            wait *= 1.6
    raise RuntimeError("unreachable")


def pages(path: str, params: dict, limit: int = 1000):
    """Every result, by offset. The API's count is not usable (it reports the largest 64-bit integer), so it stops on
    the first short page."""
    offset = 0
    while True:
        q = urllib.parse.urlencode({**params, "limit": limit, "offset": offset})
        res = get(f"{API}/{path}/?{q}")["results"]
        yield from res
        if len(res) < limit:
            return
        offset += limit


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--since", default="2011-01-01")
    a = ap.parse_args(argv)
    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = list(pages("incident", {"hazard": LANDSLIDE, "incident_on__gt": f"{a.since}T00:00:00+05:45", "ordering": "id", "expand": "loss"}))
    seen, uniq = set(), []
    for r in rows:  # offset paging over a live table can repeat a record; keep the first copy
        if r["id"] not in seen:
            seen.add(r["id"])
            uniq.append(r)
    wards = {w["id"]: w for w in pages("ward", {})}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "incidents_landslide.json").write_text(json.dumps({"retrieved_at": retrieved, "source": f"{API}/incident/?hazard={LANDSLIDE}",
                                                              "results": uniq}, ensure_ascii=False), encoding="utf-8")
    (OUT / "wards.json").write_text(json.dumps({"retrieved_at": retrieved, "source": f"{API}/ward/", "results": list(wards.values())},
                                               ensure_ascii=False), encoding="utf-8")
    dates = sorted(r["incidentOn"][:10] for r in uniq if r.get("incidentOn"))
    print(f"{len(uniq)} landslide incidents ({len(rows) - len(uniq)} repeats dropped), {dates[0]} to {dates[-1]}; {len(wards)} wards")


if __name__ == "__main__":
    main()
