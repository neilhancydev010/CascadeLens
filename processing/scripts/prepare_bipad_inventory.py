"""Dated landslide inventory from BIPAD (NDRRMA), registered for the readiness engine as dataset C1 (audit P2).

    python prepare_bipad_inventory.py      (needs data/raw/hazard/bipad from fetch_bipad.py)

Writes data/raw/hazard/bipad/bipad_landslides.csv, one row per incident, and its SOURCE.json. Both stay under data/raw,
which git ignores: BIPAD states no licence or terms of reuse (checked 13 November 2026), so the records are not
redistributed with the repository, and the readiness engine marks the licence as not established until NDRRMA confirms
terms. What the records are, and are not:
  * dates are the local (Nepal, UTC+5:45) incident date, to the day;
  * points are BIPAD's reference point for the ward or municipality, not the landslide itself: in the Trishuli area 1,826
    reports share 431 points, so a location is good to a few kilometres at best;
  * reporting grew over the years (police and local reports, backfilled for 2011 to 2019), so counts are not comparable
    from year to year, and a day with no report is not a day with no landslide.
"""
from __future__ import annotations

import collections
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import readiness as rd  # noqa: E402

RAW = ROOT / "data/raw/hazard/bipad"
LICENCE = ("Not stated: no licence or terms of reuse found on bipadportal.gov.np or its API (checked 13 November 2026); "
           "confirm with NDRRMA before publishing or relying on it")
COLUMNS = ["id", "date", "lon", "lat", "ward_id", "municipality_id", "source", "verified", "approved", "reported_on", "available_at",
           "deaths", "missing", "injured", "houses_destroyed", "roads_destroyed", "title"]


def rows(records: list[dict], wards: dict[int, dict]) -> list[dict]:
    out = []
    for r in records:
        if not r.get("incidentOn") or not r.get("point"):
            continue
        loss = r.get("loss") if isinstance(r.get("loss"), dict) else {}
        ward = wards.get((r.get("wards") or [None])[0]) or {}
        lon, lat = r["point"]["coordinates"][:2]
        out.append({"id": r["id"], "date": r["incidentOn"][:10], "lon": round(float(lon), 5), "lat": round(float(lat), 5),
                    "ward_id": (r.get("wards") or [""])[0], "municipality_id": ward.get("municipality", ""),
                    "source": r.get("source") or "", "verified": r.get("verified"), "approved": r.get("approved"),
                    "reported_on": (r.get("reportedOn") or "")[:10], "available_at": r.get("createdOn") or "",
                    "deaths": loss.get("peopleDeathCount", ""), "missing": loss.get("peopleMissingCount", ""),
                    "injured": loss.get("peopleInjuredCount", ""), "houses_destroyed": loss.get("infrastructureDestroyedHouseCount", ""),
                    "roads_destroyed": loss.get("infrastructureDestroyedRoadCount", ""), "title": r.get("title") or ""})
    return sorted(out, key=lambda x: (x["date"], x["id"]))


def main() -> None:
    doc = json.loads((RAW / "incidents_landslide.json").read_text(encoding="utf-8"))
    wards = {w["id"]: w for w in json.loads((RAW / "wards.json").read_text(encoding="utf-8"))["results"]}
    out = rows(doc["results"], wards)
    with open(RAW / "bipad_landslides.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    dates = [r["date"] for r in out]
    pts = collections.Counter((r["lon"], r["lat"]) for r in out)
    per_year = collections.Counter(d[:4] for d in dates)
    rd.write_source(RAW, dataset="C1", provider="NDRRMA, Government of Nepal (BIPAD portal)", product="BIPAD incident records, hazard: landslide",
                    version=f"API export retrieved {doc['retrieved_at'][:10]}", url_or_request_ref=doc["source"], licence=LICENCE,
                    retrieved_at=doc["retrieved_at"], available_at=doc["retrieved_at"],
                    spatial_extent=[round(min(r["lon"] for r in out), 4), round(min(r["lat"] for r in out), 4),
                                    round(max(r["lon"] for r in out), 4), round(max(r["lat"] for r in out), 4)],
                    time_extent=[dates[0], dates[-1]], variables=["event_date", "location", "source", "verified", "losses"], units={},
                    crs="EPSG:4326", resolution_m=None, missing_fraction=0.0, quality_flags=True,
                    maturity="Government incident register: police and local reports, verified flag",
                    notes=(f"{len(out)} landslide incidents in Nepal, {dates[0]} to {dates[-1]}. Points are ward or municipality reference "
                           f"points ({len(pts)} distinct), not landslide sites. Reports per year grow from {per_year.get('2016', 0)} (2016) "
                           f"to {per_year.get(dates[-1][:4], 0)} ({dates[-1][:4]}), so counts are not comparable between years, and days "
                           "without a report are not confirmed negatives. Kept under data/raw (not redistributed) until the licence is confirmed."))
    print(f"{len(out)} incidents, {dates[0]} to {dates[-1]}, {len(pts)} distinct points -> {RAW / 'bipad_landslides.csv'}")


if __name__ == "__main__":
    main()
