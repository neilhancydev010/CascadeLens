"""Register a dataset for the readiness engine: write the SOURCE.json beside it (audit P1, "Where files go").

    python register_source.py <folder> --dataset B1 --provider "NASA GES DISC" --product "IMERG V07 Late" --version V07B \\
        --licence "NASA open data" --available-at 2026-11-12T04:00:00Z --url <download url or request reference> \\
        [--variables precipitation --units precipitation=mm/h] [--maturity Late] [--time 2016-06-01 2026-10-10] [--notes "..."]

Put the files under data/raw/<domain>/<provider>/<product>/ with their original names first. Extent, CRS, resolution and,
for tables, the time span are read from the files where they can be (GeoTIFF, GeoJSON or GeoPackage, CSV with lon, lat and
date columns); anything given on the command line wins. Then run prepare_readiness.py. Downloads nothing.
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from cascade_lens import readiness as rd  # noqa: E402


def sniff(folder: pathlib.Path) -> dict:
    """What can be read from the files themselves. Every field is optional."""
    out: dict = {}
    files = sorted(p for p in folder.rglob("*") if p.is_file() and p.name != "SOURCE.json")
    tifs = [p for p in files if p.suffix.lower() in (".tif", ".tiff")]
    vecs = [p for p in files if p.suffix.lower() in (".geojson", ".gpkg")]
    csvs = [p for p in files if p.suffix.lower() == ".csv"]
    if tifs:
        import rasterio
        from rasterio.warp import transform_bounds
        boxes, res = [], []
        with rasterio.open(tifs[0]) as d:
            out["crs"] = d.crs.to_string() if d.crs else None
        for t in tifs:
            with rasterio.open(t) as d:
                if d.crs:
                    boxes.append(transform_bounds(d.crs, "EPSG:4326", *d.bounds))
                    res.append(abs(d.transform.a) if d.crs.is_projected else abs(d.transform.a) * 111320)
        if boxes:
            out["spatial_extent"] = [round(min(b[0] for b in boxes), 4), round(min(b[1] for b in boxes), 4), round(max(b[2] for b in boxes), 4), round(max(b[3] for b in boxes), 4)]
            out["resolution_m"] = round(min(res), 1)
    elif vecs:
        import geopandas as gpd
        g = gpd.read_file(vecs[0])
        out["crs"] = g.crs.to_string() if g.crs else None
        b = g.to_crs(4326).total_bounds if g.crs else g.total_bounds
        out["spatial_extent"] = [round(float(v), 4) for v in b]
    elif csvs:
        with open(csvs[0], newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        cols = {c.lower(): c for c in (rows[0].keys() if rows else [])}
        lon, lat = cols.get("lon") or cols.get("longitude"), cols.get("lat") or cols.get("latitude")
        when = cols.get("date") or cols.get("time") or cols.get("datetime") or cols.get("timestamp")
        if lon and lat:
            xs = [float(r[lon]) for r in rows if r[lon]]
            ys = [float(r[lat]) for r in rows if r[lat]]
            out["spatial_extent"] = [round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4)]
            out["crs"] = "EPSG:4326"
        if when:
            ts = sorted(r[when][:10] for r in rows if r[when])
            out["time_extent"] = [ts[0], ts[-1]]
        out["variables"] = [c for c in (rows[0].keys() if rows else []) if c not in (lon, lat, when)]
    return out


def main(argv=None) -> pathlib.Path:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("folder", type=pathlib.Path)
    ap.add_argument("--dataset", required=True, help="Catalogue ID, such as B1 or C1 (processing/configs/readiness.json)")
    for k in ("provider", "product", "version", "licence", "url", "available-at", "maturity", "notes", "crs"):
        ap.add_argument(f"--{k}")
    ap.add_argument("--variables", nargs="*")
    ap.add_argument("--units", nargs="*", default=[], help="variable=unit pairs")
    ap.add_argument("--time", nargs=2, metavar=("START", "END"))
    ap.add_argument("--extent", nargs=4, type=float, metavar=("W", "S", "E", "N"))
    ap.add_argument("--resolution-m", type=float)
    ap.add_argument("--missing-fraction", type=float)
    ap.add_argument("--quality-flags", action="store_true")
    a = ap.parse_args(argv)
    if not a.folder.is_dir():
        raise SystemExit(f"{a.folder} is not a folder: put the files there first")
    meta = sniff(a.folder)
    given = {"provider": a.provider, "product": a.product, "version": a.version, "licence": a.licence, "url_or_request_ref": a.url,
             "available_at": getattr(a, "available_at"), "maturity": a.maturity, "notes": a.notes, "crs": a.crs,
             "variables": a.variables, "units": dict(u.split("=", 1) for u in a.units) or None,
             "time_extent": list(a.time) if a.time else None, "spatial_extent": list(a.extent) if a.extent else None,
             "resolution_m": a.resolution_m, "missing_fraction": a.missing_fraction, "quality_flags": a.quality_flags or None}
    meta.update({k: v for k, v in given.items() if v is not None})
    meta["retrieved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    p = rd.write_source(a.folder, dataset=a.dataset, **meta)
    print(p)
    return p


if __name__ == "__main__":
    main()
