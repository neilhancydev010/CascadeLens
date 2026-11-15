"""IMERG daily rainfall for the Trishuli area, one GeoTIFF stack per year, registered as datasets B1 and C5 (audit P2).

    python prepare_rainfall.py [--collection GPM_3IMERGDL.07]      (needs the subsets from fetch_imerg.py)

Writes data/reference/rainfall/<collection>/imerg_<year>.tif (one band per UTC day, mean precipitation rate in mm/h, the
unit the readiness catalogue asks for: multiply by 24 for the day's total in mm), imerg_cnt_<year>.tif (how many of the
48 half-hourly retrievals were valid that day: the quality flag), days.csv (band order, date, file version and the time
each day was published) and SOURCE.json. NASA data, open to reuse with citation, so these files are committed.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
from datetime import date, datetime, time, timedelta, timezone

import h5py
import numpy as np
import rasterio
from rasterio.transform import from_origin

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import readiness as rd  # noqa: E402

FILL = -9999.0
DOI = {"GPM_3IMERGDL.07": "10.5067/GPM/IMERGDL/DAY/07", "GPM_3IMERGDF.07": "10.5067/GPM/IMERGDF/DAY/07"}
LATENCY_H = {"GPM_3IMERGDL.07": 14, "GPM_3IMERGDF.07": 24 * 105}  # Late: about 14 h after the day; Final: about 3.5 months
LICENCE = "NASA open data: no restrictions on reuse, cite the dataset DOI (EOSDIS data use guidance)"


def read_day(p: pathlib.Path) -> tuple[date, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(UTC day, lon centres, lat centres, rate mm/h as [lat north to south, lon], valid half-hour count) for one subset."""
    with h5py.File(p) as f:
        day = date(1980, 1, 6) + timedelta(days=float(f["time"][0]))
        lon, lat = f["lon"][:].astype(float), f["lat"][:].astype(float)
        mm_day = f["precipitation"][0].astype(float)  # [lon, lat], mm/day (daily mean rate)
        cnt = f["precipitation_cnt"][0].astype(int)
    rate = np.where(mm_day <= FILL + 1, np.nan, mm_day / 24.0)
    return day, lon, lat, rate.T[::-1], cnt.T[::-1]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--collection", default="GPM_3IMERGDL.07")
    a = ap.parse_args(argv)
    src = ROOT / "data/raw/rainfall/gesdisc" / a.collection
    out = ROOT / "data/reference/rainfall" / a.collection
    files = sorted(src.rglob("*.subset.nc4"))
    if not files:
        raise SystemExit(f"no subsets under {src}: run fetch_imerg.py first")
    by_year: dict[int, list] = {}
    for p in files:
        day, lon, lat, rate, cnt = read_day(p)
        by_year.setdefault(day.year, []).append((day, p.name.split(".")[-4], rate, cnt))
    lat_n = lat[::-1]
    transform = from_origin(lon[0] - 0.05, lat_n[0] + 0.05, 0.1, 0.1)
    out.mkdir(parents=True, exist_ok=True)
    rows, n_cells, n_missing, low_cnt = [], 0, 0, 0
    for year, days in sorted(by_year.items()):
        days.sort(key=lambda d: d[0])
        stack = np.stack([np.where(np.isnan(r), FILL, np.round(r, 3)) for _, _, r, _ in days]).astype("float32")
        counts = np.stack([np.clip(c, 0, 255) for _, _, _, c in days]).astype("uint8")
        prof = dict(driver="GTiff", width=stack.shape[2], height=stack.shape[1], crs="EPSG:4326", transform=transform,
                    compress="deflate", tiled=False)
        with rasterio.open(out / f"imerg_{year}.tif", "w", count=len(days), dtype="float32", nodata=FILL, predictor=3, **prof) as d:
            d.write(stack)
            d.update_tags(units="mm/h", quantity="daily mean precipitation rate (multiply by 24 for mm per day)", day="UTC", doi=DOI[a.collection])
            for i, (day, *_rest) in enumerate(days, 1):
                d.set_band_description(i, day.isoformat())
        with rasterio.open(out / f"imerg_cnt_{year}.tif", "w", count=len(days), dtype="uint8", predictor=2, **prof) as d:
            d.write(counts)
            d.update_tags(units="count", quantity="valid half-hourly retrievals in the day (48 = all)")
            for i, (day, *_rest) in enumerate(days, 1):
                d.set_band_description(i, day.isoformat())
        for i, (day, version, rate, cnt) in enumerate(days, 1):
            published = datetime.combine(day + timedelta(days=1), time(0), timezone.utc) + timedelta(hours=LATENCY_H[a.collection])
            rows.append({"date": day.isoformat(), "file": f"imerg_{year}.tif", "band": i, "version": version,
                         "available_at": published.isoformat().replace("+00:00", "Z")})
        n_cells += stack.size
        n_missing += int((stack == FILL).sum())
        low_cnt += int((counts < 24).sum())
    with open(out / "days.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    span = [rows[0]["date"], rows[-1]["date"]]
    expected = (date.fromisoformat(span[1]) - date.fromisoformat(span[0])).days + 1
    versions = sorted({r["version"] for r in rows})
    extent = [round(lon[0] - 0.05, 4), round(lat_n[-1] - 0.05, 4), round(lon[-1] + 0.05, 4), round(lat_n[0] + 0.05, 4)]
    common = dict(provider="NASA GES DISC", product=f"GPM IMERG {'Late' if 'DL' in a.collection else 'Final'} Precipitation L3 1 day 0.1 degree ({a.collection})",
                  version=", ".join(versions), url_or_request_ref=f"https://doi.org/{DOI[a.collection]}", licence=LICENCE,
                  retrieved_at=datetime.now(timezone.utc).date().isoformat(), available_at=rows[-1]["available_at"],
                  spatial_extent=extent, time_extent=span, variables=["precipitation", "precipitation_cnt"],
                  units={"precipitation": "mm/h", "precipitation_cnt": "count"}, crs="EPSG:4326", resolution_m=round(0.1 * 111320, 1),
                  missing_fraction=round(n_missing / n_cells, 4), quality_flags=True,
                  maturity="Late run (near real time, no gauge adjustment)" if "DL" in a.collection else "Final run (gauge adjusted)")
    note = (f"{len(rows)} of {expected} UTC days, {len(by_year)} yearly stacks of {len(lat)} x {len(lon)} cells. Each band is the day's mean "
            f"rate in mm/h (x 24 for mm). Days are UTC; Nepal is UTC+5:45. Each day was published about {LATENCY_H[a.collection]} h after it "
            f"ended (days.csv), which a backtest must respect. {low_cnt} cell-days have fewer than half their half-hourly retrievals. "
            "History is the V07 reprocessing, not the values issued at the time.")
    rd.write_source(out, dataset="B1", notes=note, **common)
    rd.write_source(ROOT / "data/metadata/sources/C5", dataset="C5", notes=note + f" Files: {out.relative_to(ROOT).as_posix()}. "
                    "IMERG only: the DHM daily gauges this dataset also lists need a DHM API key, which the project does not hold.", **common)
    print(f"{len(rows)} days {span[0]} to {span[1]} ({expected - len(rows)} missing), versions {versions}, "
          f"missing cells {n_missing / n_cells:.4%} -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
