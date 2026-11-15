"""ASF catalogue discovery for NISAR granules. Catalogue records only: says nothing about data accessibility."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

BBOX = (84.3976, 27.7320, 85.5508, 28.3500)  # W, S, E, N  (catalogue search envelope, EPSG:4326)
PRODUCTS = ("GUNW", "GOFF", "GCOV", "GSLC")


@dataclass
class Granule:
    product: str
    file_id: str
    direction: str
    track: int
    frame: int | None
    ref_date: str  # YYYY-MM-DD (GUNW/GOFF reference acquisition; GCOV/GSLC acquisition)
    sec_date: str | None
    url: str | None
    size_mb: float | None
    geometry: dict | None = None  # catalogue footprint, GeoJSON. Coverage of the frame, not of valid pixels
    sidecars: dict | None = None  # small QA and browse files, so a granule can be judged before a multi-GB download


def _d(s: str) -> str:
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def parse_file_id(file_id: str) -> dict:
    """Parse a NISAR granule name. Layout verified against live ASF records:
    NISAR_L2_PR_GUNW_<cyc>_<trk>_<A|D>_<frame>_<cyc>_<mode>_<pol>_<refStart>_<refEnd>_<secStart>_<secEnd>_...
    GCOV/GSLC have a single acquisition: ..._<start>_<end>_...
    """
    p = file_id.split("_")
    prod = p[3]
    out = {"product": prod, "track": int(p[5]), "direction": {"A": "ASCENDING", "D": "DESCENDING"}[p[6]], "frame": int(p[7])}
    stamps = [x for x in p if len(x) == 15 and x[8] == "T" and x[:8].isdigit()]
    out["ref_date"] = _d(stamps[0]) if stamps else None
    out["sec_date"] = _d(stamps[2]) if prod in ("GUNW", "GOFF") and len(stamps) >= 3 else None
    return out


def search(start: str, end: str, products=PRODUCTS, max_results=500) -> list[Granule]:
    import asf_search as asf

    w, s, e, n = BBOX
    wkt = f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"
    out: list[Granule] = []
    for prod in products:
        res = asf.geo_search(platform=asf.PLATFORM.NISAR, processingLevel=prod, intersectsWith=wkt,
                             start=start, end=end, maxResults=max_results)
        for r in res:
            pr = r.properties
            fid = pr["fileID"]
            info = parse_file_id(fid)
            out.append(Granule(info["product"], fid, info["direction"], info["track"], info["frame"],
                               info["ref_date"], info["sec_date"], pr.get("url"), _h5_mb(pr.get("bytes"), fid), r.geometry,
                               sidecar_urls(r.umm.get("RelatedUrls", []))))
    return out


SIDECARS = ("_QA_SUMMARY.csv", "_QA_REPORT.pdf", "_LATLON.kml", "_LATLON.png")


def sidecar_urls(related: list[dict]) -> dict:
    """Pick the HTTPS QA and browse links ASF publishes for a granule, keyed by suffix."""
    urls = [u["URL"] for u in related if u["URL"].startswith("https://")]
    return {s: u for s in SIDECARS for u in urls if u.endswith(s)}


def _h5_mb(sizes: dict | None, file_id: str) -> float | None:
    """ASF `bytes` maps every file in the granule to {bytes, format}; we want the science HDF5."""
    entry = (sizes or {}).get(f"{file_id}.h5")
    return round(entry["bytes"] / 1e6, 1) if entry else None


def dump(granules: list[Granule], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(g) for g in granules], f, indent=1)
