"""Readiness of every flood and landslide capability, from the data actually on disk (audit P1).

    python prepare_readiness.py [--now 2026-11-13T00:00:00Z]

1. Writes a SOURCE.json for each dataset the repository already ships (group A), under data/metadata/sources, read from
   the files themselves: extent, CRS, resolution, dates.
2. Reads every SOURCE.json under data/metadata/sources, data/reference and data/raw, and every model, calibration, validation or
   operational record under data/metadata/evidence.
3. Writes frontend/public/data/readiness.json: each capability's earned state, the check behind it and the next requirement.
Downloads nothing. A dataset counts only when its SOURCE.json is on disk.
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone

import rasterio
from rasterio.warp import transform_bounds

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import readiness as rd  # noqa: E402

PUB = ROOT / "frontend/public/data"
SOURCES = ROOT / "data/metadata/sources"
EVIDENCE = ROOT / "data/metadata/evidence"


def vector_extent(*paths: pathlib.Path) -> list[float]:
    xs, ys = [], []
    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c:
                walk(x)
    for p in paths:
        for f in json.loads(p.read_text(encoding="utf-8"))["features"]:
            walk(f["geometry"]["coordinates"])
    return [round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4)]


def shipped_sources() -> None:
    m = json.loads((PUB / "manifests/manifest.json").read_text(encoding="utf-8"))
    env = [round(v, 4) for v in m["caseStudy"]["searchEnvelope"]]
    nisar = [g for g in m["granules"] if g.get("product") in ("GUNW", "GOFF") and g.get("status") in ("prepared", "sampleable", "qa_passed")]
    dates = sorted(str(d) for g in nisar for d in (g.get("ref_date"), g.get("sec_date")) if d)
    rd.write_source(SOURCES / "A1", dataset="A1", provider="NASA/JPL, ISRO via ASF DAAC", product="NISAR L2 GUNW and GOFF, prepared",
                    version=", ".join(sorted({g["file_id"].split("_")[-5] for g in nisar})), url_or_request_ref="data/metadata/catalogue.json",
                    licence="NASA open data (attribution required)", retrieved_at=None, available_at=None, spatial_extent=env,
                    time_extent=[dates[0][:10], dates[-1][:10]] if dates else None, variables=["unwrapped_phase", "coherence", "offsets"],
                    units={"unwrapped_phase": "radians", "coherence": "1"}, crs="EPSG:32645", resolution_m=80, missing_fraction=None,
                    quality_flags=True, maturity="Provisional", notes=f"{len(nisar)} granules in the manifest")
    dem = PUB / "sampling/context/copdem_glo30.tif"
    with rasterio.open(dem) as d:
        ext = [round(v, 4) for v in transform_bounds(d.crs, "EPSG:4326", *d.bounds)]
        res = round(abs(d.transform.a) if d.crs.is_projected else abs(d.transform.a) * 111320, 1)
        crs = d.crs.to_string()
    rd.write_source(SOURCES / "A2", dataset="A2", provider="ESA / Airbus, Copernicus DEM", product="GLO-30, study area clip", version="2021 release",
                    url_or_request_ref="https://copernicus-dem-30m.s3.amazonaws.com", licence="Copernicus DEM licence (free, with attribution)",
                    retrieved_at=None, available_at=None, spatial_extent=ext, time_extent=["2011-01-01", "2015-12-31"], variables=["elevation"],
                    units={"elevation": "m"}, crs=crs, resolution_m=min(res, 30), missing_fraction=0.0, quality_flags=False, maturity="Released",
                    notes="Clip to the search envelope only; the upstream Trishuli catchment in Tibet is not covered")
    v = PUB / "vectors"
    rd.write_source(SOURCES / "A3", dataset="A3", provider="UNOSAT / UNITAR", product="FL20260826NPL event mapping", version="Preliminary",
                    url_or_request_ref="https://data.humdata.org/dataset/mudflow-rockflow-impact-assessment-in-rasuwa-nuwakot-districts-bagmati-province-nepal-as-o",
                    licence="CC BY-SA", retrieved_at=None, available_at=None,
                    spatial_extent=vector_extent(v / "unosat_mudflow_extent.geojson", v / "unosat_detachment_zone.geojson"),
                    time_extent=["2026-08-26", "2026-08-28"], variables=["mudflow_extent", "detachment_zone", "affected_roads", "affected_buildings"],
                    units={}, crs="EPSG:4326", resolution_m=None, missing_fraction=None, quality_flags=True, maturity="Preliminary",
                    notes="FieldValidation = 0: not field validated")
    rd.write_source(SOURCES / "A4", dataset="A4", provider="OpenStreetMap contributors via HOT", product="Roads, rivers, places, facilities, destroyed features, bridge reports",
                    version="HOT export, 2026", url_or_request_ref="https://data.humdata.org/dataset/hot_flood_npl", licence="ODbL",
                    retrieved_at=None, available_at=None, spatial_extent=vector_extent(v / "osm_roads.geojson"), time_extent=["2026-08-26", "2026-11-13"],
                    variables=["roads", "rivers", "places", "health_facilities", "helipads", "road_states"], units={}, crs="EPSG:4326",
                    resolution_m=None, missing_fraction=None, quality_flags=False, maturity="Community-maintained",
                    notes="Post-event mapping; incomplete")
    # C7: the repeat GUNW series, as shipped: one coherence step per pair, for every track with a series (Track 48 frame 74,
    # Track 98 frame 16), plus the frames observability assessed
    series = [l for l in m["layers"] if l["id"].startswith(f"{m['caseStudy']['id']}:coherence-timeline") and l.get("timeSteps")]
    if series:
        steps = [st for l in series for st in l["timeSteps"]]
        pairs = [s["label"].split("/") for s in steps]
        srcs = [s for st in steps for s in st["sources"]]
        b = [s["bounds"] for s in srcs]
        views = [m.get("observability") or {}, *(m.get("observabilityViews") or {}).values()]
        frames = sorted({f"{v['track']}/{f['frame']}" for v in views if v for f in v.get("frames") or [{"frame": v.get("frame")}]})
        tracks = ", ".join(f"Track {l['track']} {str(l.get('orbitDirection', '')).lower()} frame{'s' if len(l['frames']) > 1 else ''} {' and '.join(map(str, l['frames']))} ({len(l['timeSteps'])} pairs)" for l in series)
        rd.write_source(SOURCES / "C7", dataset="C7", provider="NASA/JPL, ISRO via ASF DAAC", product=f"NISAR L2 GUNW repeat series: {tracks}",
                        version=", ".join(sorted({s["granule"].split("_")[-5] for s in srcs})), url_or_request_ref="data/metadata/catalogue.json",
                        licence="NASA open data (attribution required)", retrieved_at=None, available_at=None,
                        spatial_extent=[round(min(x[0] for x in b), 4), round(min(x[1] for x in b), 4), round(max(x[2] for x in b), 4), round(max(x[3] for x in b), 4)],
                        time_extent=[min(p[0] for p in pairs), max(p[1] for p in pairs)], variables=["coherence"], units={"coherence": "1"},
                        crs="EPSG:32645", resolution_m=80, missing_fraction=None, quality_flags=True, maturity="Provisional",
                        notes=f"{len(pairs)} pairs as coherence through time; track/frame assessed for observability: "
                              f"{', '.join(frames)}. Phase is not converted to displacement")


def main(argv: list[str]) -> None:
    now = datetime.fromisoformat(argv[argv.index("--now") + 1].replace("Z", "+00:00")) if "--now" in argv else datetime.now(timezone.utc)
    shipped_sources()
    catalogue = json.loads((ROOT / "processing/configs/readiness.json").read_text(encoding="utf-8"))
    sources = rd.load_sources(SOURCES, ROOT / "data/reference", ROOT / "data/raw")
    for meta in (m for ms in sources.values() for m in ms):
        meta["_path"] = str(pathlib.Path(meta["_path"]).relative_to(ROOT).as_posix()) if meta["_path"].startswith(str(ROOT)) else meta["_path"]
    evidence = {}
    for p in sorted(EVIDENCE.glob("*.json")) if EVIDENCE.exists() else []:
        rec = json.loads(p.read_text(encoding="utf-8"))
        evidence[rec["key"]] = rec
    out = rd.run(catalogue, sources, evidence, now)
    out["datasets"] = {k: {**v, "onDisk": bool(sources.get(k))} for k, v in catalogue["datasets"].items()}
    (PUB / "readiness.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for c in out["capabilities"]:
        print(f"{c['capability']:<14} {c['state']:<36} next: {c['next_requirement']}")


if __name__ == "__main__":
    main(sys.argv[1:])
