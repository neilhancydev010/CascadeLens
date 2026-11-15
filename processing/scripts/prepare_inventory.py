"""Nepal subset of NASA's Global Landslide Catalog, registered for the readiness engine as dataset C1 (audit P2).

    python prepare_inventory.py      (needs data/raw/context/nasa_glc from fetch_context.py)

Writes data/reference/hazard/nasa-glc/glc_nepal.csv (ISO dates, original columns kept) and its SOURCE.json. The catalogue
is compiled from media and reports: places with no record are not confirmed negatives, and most locations here are
accurate to 5 km or worse, too coarse for a 30 m susceptibility model. The readiness engine judges it; nothing is fitted.
"""
from __future__ import annotations

import collections
import csv
import json
import pathlib
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import readiness as rd  # noqa: E402

RAW = ROOT / "data/raw/context/nasa_glc/Global_Landslide_Catalog_Export_rows.csv"
OUT = ROOT / "data/reference/hazard/nasa-glc"


def iso(s: str) -> str | None:
    for f in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y"):
        try:
            return datetime.strptime(s.strip(), f).date().isoformat()
        except ValueError:
            pass
    return None


def main() -> None:
    rows = [r for r in csv.DictReader(open(RAW, encoding="utf-8")) if r.get("country_name") == "Nepal"]
    for r in rows:
        r["event_date"] = iso(r["event_date"]) or ""
    rows.sort(key=lambda r: (r["event_date"], r["event_id"]))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "glc_nepal.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    dates = sorted(r["event_date"] for r in rows if r["event_date"])
    lon, lat = [float(r["longitude"]) for r in rows], [float(r["latitude"]) for r in rows]
    acc = collections.Counter(r["location_accuracy"] for r in rows)
    trig = collections.Counter(r["landslide_trigger"] for r in rows)
    src = json.loads((ROOT / "processing/configs/context_sources.json").read_text(encoding="utf-8"))["nasa_glc"]
    rd.write_source(OUT, dataset="C1", provider="NASA Goddard Space Flight Center", product="Global Landslide Catalog (Nepal subset)",
                    version="Export as published on data.nasa.gov", url_or_request_ref=src["url"], licence=src["licence"], retrieved_at="2026-11-13",
                    available_at=None, spatial_extent=[round(min(lon), 4), round(min(lat), 4), round(max(lon), 4), round(max(lat), 4)],
                    time_extent=[dates[0], dates[-1]], variables=["event_date", "landslide_category", "landslide_trigger", "location_accuracy", "fatality_count"],
                    units={}, crs="EPSG:4326", resolution_m=None, missing_fraction=round(1 - len(dates) / len(rows), 3), quality_flags=True,
                    maturity="Catalogue compiled from media and reports",
                    notes=(f"{len(rows)} Nepal events, {dates[0]} to {dates[-1]}. Location accuracy: "
                           + ", ".join(f"{k} {v}" for k, v in sorted(acc.items(), key=lambda kv: -kv[1]))
                           + ". Triggers: " + ", ".join(f"{k} {v}" for k, v in trig.most_common(4))
                           + ". Unrecorded places are not confirmed negatives."))
    print(f"{len(rows)} Nepal events, {dates[0]} to {dates[-1]}; accuracy {dict(acc)}")


if __name__ == "__main__":
    main()
