"""Builds the frontend manifest from what is really on disk. A layer's status comes from files and QA records, never from config."""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

from . import nisar, pipeline

CASE_STUDY = {"id": "rasuwa-2026", "name": "Rasuwa–Bhote Koshi–Trishuli, Nepal", "eventDate": "2026-08-26"}
USABLE = ("prepared", "renderable", "sampleable")
ORDER = ["catalogued", "downloaded", "inspected", "qa_passed", "prepared", "renderable", "sampleable"]
CATEGORY = {"GUNW": "gunw", "GOFF": "goff", "GCOV": "gcov"}
UNITS_NOTE = {"gunw-phase": "Radians, per product attribute. Not a displacement. Colours show each value relative to its frame's median; the inspector shows the stored value.",
              "gunw-phase-iono": "Radians. Not a displacement. Colours are relative to each frame's median.", "gunw-iono": "Radians. Colours are relative to each frame's median.", "gunw-coherence": "Dimensionless, 0–1.",
              "goff-range": "Metres in radar slant range, not east/west.", "goff-azimuth": "Metres along the satellite track, not north/south.",
              "gcov-backscatter": "Displayed in dB (10·log10) from the linear gamma-0 term; the inspector reports both."}
LIMITS = {
    "gunw-phase": ["Phase is not displacement. No LOS conversion is applied: neither the specification nor the ATBD states the phase sign convention.",
                   "Pixels with component label 0 are masked: the ATBD says they could not be reliably unwrapped.",
                   "The estimated ionospheric phase screen is included in GUNW but not applied.", "Frames 74 and 75 are unwrapped separately and are not mosaicked.",
                   "The 12-day interval cannot date a change or attribute its cause."],
    "gunw-coherence": ["Low coherence limits phase interpretation. It is not evidence of a landslide or its extent."],
    "gunw-cc": ["Label numbers are arbitrary identifiers. Label 0 means not reliably unwrapped and belongs to no component."],
    "gunw-phase-iono": ["Derived here: phase minus the published ionosphere screen. Not a product of the NISAR project.", "The sign was chosen from the ATBD equation and confirmed by scatter on these frames, not from a stated convention.",
                        "The screen is low-frequency only, so smaller ionospheric effects remain. Troposphere and terrain effects also remain.", "Still phase, not displacement."],
    "gunw-iono": ["An estimate published in the product. It is shown for comparison and is not applied to the phase here.", "Low-frequency only, per the ATBD: small-scale ionospheric effects are not captured."],
    "goff-range": ["Raw, unculled and unfiltered: expect outliers.", "A radar-geometry component, not a geographic vector.", "Layer 3 uses the smallest search window, so a very large shift may not be found."],
    "goff-azimuth": ["Raw, unculled and unfiltered: expect outliers.", "A radar-geometry component, not a geographic vector.", "Layer 3 uses the smallest search window, so a very large shift may not be found."],
    "goff-snr": ["No SNR threshold is applied yet: it needs the real data distribution."],
    "goff-peak": ["A matching-quality indicator, not a movement measurement."],
    "gcov-backscatter": ["A single-date snapshot, not a damage or flood classification.", "Do not difference 28 and 31 August: their orbit geometries differ."],
}


def _load(path, default):
    p = pathlib.Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def maturity(ident: dict, crid: str) -> str:
    """From the file's own DOI, which ends -B1 for Beta and -P1 for Provisional. Until a file is read, only the catalogue speaks."""
    if not ident:
        return f"Provisional per catalogue ({crid}); confirm from file"
    doi = str(ident.get("productDoi") or "")
    name = {"B": "Beta", "P": "Provisional", "V": "Validated"}.get(doi.rsplit("-", 1)[-1][:1], "Unknown")
    return f"{name} ({ident.get('compositeReleaseId')})"


def _status(granules: list[dict], states: dict, raw: pathlib.Path) -> tuple[str, str | None]:
    """Worst-case reason across a layer's frames, because one prepared frame must not hide a failed one."""
    if not granules:
        return "unavailable", "No catalogue record for this combination."
    seen = []
    for g in granules:
        s = states.get(g["file_id"])
        if s:
            seen.append((s["status"], s.get("reason")))
        elif pipeline.granule_path(raw, g).exists():
            seen.append(("downloaded", "Downloaded, not yet processed. Run process_nisar.py."))
        else:
            seen.append(("catalogued", "Listed in the ASF catalogue, not retrieved. NASA Earthdata Login required to download it."))
    for bad in ("invalid", "unavailable"):
        for st, why in seen:
            if st == bad:
                return st, why
    return min(seen, key=lambda x: ORDER.index(x[0]))


def nisar_layers(catalogue, cfg, states, fragments, raw) -> list[dict]:
    selected = pipeline.select_granules(catalogue, cfg)
    out = []
    for g in pipeline.groups(cfg):
        grs = [x for x in selected if x["group"] == g["id"] and x["product"] == g["product"]]
        status, reason = _status(grs, states, raw)
        for mid in pipeline.GROUP_PRODUCTS[g["product"]] + pipeline.DERIVED.get(g["product"], ()):
            m = nisar.MEASUREMENTS[mid]
            lid = f"{g['id']}:{mid}"
            f = fragments.get(lid)
            ident = next((states[x["file_id"]].get("identification") for x in grs if x["file_id"] in states), None) or {}
            layer = {"id": lid, "groupId": g["id"], "name": m["name"], "category": CATEGORY[g["product"]], "mission": "NISAR", "instrument": "L-SAR",
                     "productType": g["product"], "measurementClass": "derived" if not m["path"] else "measurement", "measurementType": mid, "kind": m["kind"], "units": m["units"], "unitsNote": UNITS_NOTE.get(mid),
                     "acquisition": {"reference": g["ref_date"], "secondary": g["sec_date"]}, "orbitDirection": g["direction"], "track": g["track"], "frames": g["frames"],
                     "qualityLayerIds": [f"{g['id']}:{q}" for q in m["quality"]], "status": status, "statusReason": reason, "sources": [],
                     "productMaturity": maturity(ident, cfg["crid"]),
                     "sourceGranules": [x["file_id"] for x in grs], "attribution": "NASA/JPL-Caltech/ISRO, NISAR; distributed by ASF DAAC", "limitations": LIMITS[mid]}
            if f and status in ("qa_passed", *USABLE):
                layer |= {"status": "sampleable", "statusReason": None, "units": f["units"] or m["units"], "postingM": f["postingM"], "crs": f"EPSG:{f['epsg']}",
                          "sources": f["sources"], "stats": f["stats"], "polarization": f["polarization"], "displayDb": f["displayDb"], "goffLayer": f["goffLayer"],
                          "displayRelative": f.get("displayRelative", False), "legend": {"type": m["kind"], "stops": f["stops"], "min": f["stats"].get("displayMin"), "max": f["stats"].get("displayMax"),
                                     "labels": f["stats"].get("labels"), "unit": "dB" if f["displayDb"] else (f"{f['units']}, relative to frame median" if f.get("displayRelative") else f["units"])},
                          "processingHistory": {"processedAt": f["processedAt"], "parameters": f["parameters"], "provenance": f.get("provenance")}}
            out.append(layer)
    return out


def build(root: pathlib.Path, cfg: dict) -> dict:
    meta = root / "data" / "metadata"
    catalogue = _load(meta / "catalogue.json", [])
    states = {s["file_id"]: s for p in sorted((meta / "granules").glob("*.json")) if (s := _load(p, None))}
    fragments = {f["layerId"]: f for p in sorted((meta / "prepared").glob("*__*.json")) if (f := _load(p, None))}
    context = _load(meta / "prepared" / "context.json", {"layers": [], "bookmarks": []})
    measured = nisar_layers(catalogue, cfg, states, fragments, root / "data" / "raw")
    have = {(x["groupId"], x["productType"]) for x in measured if x["status"] in USABLE}
    previews = [p for p in _load(meta / "prepared" / "previews.json", []) if (p["groupId"], p["productType"]) not in have]  # A picture never sits beside the real measurement
    layers = measured + previews + context["layers"]
    selected = pipeline.select_granules(catalogue, cfg)
    grps = [{"id": p["id"], "kind": "pair", "label": p["label"], "role": p["role"], "direction": p["direction"], "track": p["track"], "frames": p["frames"],
             "reference": p["ref_date"], "secondary": p["sec_date"], "products": p["products"]} for p in cfg["pairs"]]
    grps += [{"id": s["id"], "kind": "snapshot", "label": s["label"], "role": "Post-event radar backscatter snapshot", "direction": s["direction"], "track": s["track"],
              "frames": s["frames"], "reference": s["date"], "secondary": None, "products": ["GCOV"]} for s in cfg["snapshots"]]
    for g in grps:
        ls = [x for x in layers if x.get("groupId") == g["id"]]
        g["available"] = any(x["status"] in USABLE and x["category"] != "preview" for x in ls)
        g["statusReason"] = None if g["available"] else next((x["statusReason"] for x in ls), None)
    return {"schemaVersion": 1, "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fixture": bool(cfg.get("fixture")), "fixtureLabel": cfg.get("fixture_label"),
            "analysis": {p.stem.removesuffix("-analysis"): _load(p, None) for p in sorted((root / "data" / "qa").glob("*-analysis.json"))},
            "caseStudy": {**CASE_STUDY, "searchEnvelope": cfg["aoi_bbox"]}, "bookmarks": context["bookmarks"], "groups": grps, "layers": layers,
            "granules": [{k: g.get(k) for k in ("file_id", "group", "product", "frame", "direction", "track", "ref_date", "sec_date", "size_mb", "geometry")}
                         | {"status": states.get(g["file_id"], {}).get("status", "catalogued")} for g in selected]}


def validate(manifest: dict, public_root: pathlib.Path) -> list[str]:
    """Every asset a usable layer points to must exist, and pending layers must not point to anything."""
    errors = []
    for l in manifest["layers"]:
        usable = l["status"] in USABLE
        if not usable and l.get("sources"):
            errors.append(f"{l['id']}: status {l['status']} but has sources")
        if usable and not (l.get("sources") or l.get("vector")):
            errors.append(f"{l['id']}: usable without assets")
        for s in l.get("sources", []):
            for k in ("sampling", "validity"):
                if s.get(k) and not (public_root / s[k]).exists():
                    errors.append(f"{l['id']}: missing {s[k]}")
            if s.get("tiles") and not (public_root / s["tiles"]["url"].split("/{z}")[0]).is_dir():
                errors.append(f"{l['id']}: missing tiles")
        if l.get("vector") and not (public_root / l["vector"]["url"]).exists():
            errors.append(f"{l['id']}: missing {l['vector']['url']}")
    return errors
