"""Emergency mode: NISAR browse PNGs as clearly labelled pictures when a science file cannot be retrieved.

A browse image holds colours, not measurements. It is `renderable`, never `sampleable`, and QA does not apply to it.
"""
from __future__ import annotations

import pathlib
import re

import numpy as np
from PIL import Image
from rasterio.control import GroundControlPoint
from rasterio.transform import from_gcps

from . import export
from .manifest import CATEGORY

LIMITS = ["A browse picture only: it holds colours, not measurements, so nothing here can be sampled or interpreted quantitatively.",
          "Placed from the four corners in its KML, so its position is approximate.", "Not quality checked. It stands in for a science file that could not be retrieved."]


def parse_kml_quad(text: str) -> list[tuple[float, float]]:
    """gx:LatLonQuad corners as (lon, lat), counter-clockwise from lower left."""
    m = re.search(r"<coordinates>(.*?)</coordinates>", text, re.S)
    if not m:
        raise ValueError("KML has no coordinates")
    pts = [tuple(float(v) for v in p.split(",")[:2]) for p in m.group(1).split()]
    if len(pts) != 4:
        raise ValueError(f"expected 4 corners, found {len(pts)}")
    return pts


def build_source(png, kml, tiles_dir, zmin: int, zmax: int) -> dict:
    img = np.array(Image.open(png).convert("RGBA"))
    h, w = img.shape[:2]
    quad = parse_kml_quad(pathlib.Path(kml).read_text(encoding="utf-8"))
    pixels = [(h, 0), (h, w), (0, w), (0, 0)]  # Same order as the quad
    transform = from_gcps([GroundControlPoint(r, c, x, y) for (r, c), (x, y) in zip(pixels, quad)])
    lons, lats = zip(*quad)
    bounds = [min(lons), min(lats), max(lons), max(lats)]
    rgba, x0, y0 = export.warp_rgba(np.moveaxis(img, -1, 0), transform, "EPSG:4326", bounds, zmax)
    n = export.write_pyramid(rgba, x0, y0, zmax, zmin, tiles_dir)
    return {"bounds": bounds, "minzoom": zmin, "maxzoom": zmax, "count": n}


def prepare(granules: list[dict], qa_dir, public, cfg: dict) -> list[dict]:
    """One preview layer per observation and product, for the frames whose sidecars are on disk."""
    qa_dir, public = pathlib.Path(qa_dir), pathlib.Path(public)
    zmin, zmax = cfg["tile_zoom"][0], 11
    grouped: dict = {}
    for g in granules:
        png, kml = qa_dir / f"{g['file_id']}_LATLON.png", qa_dir / f"{g['file_id']}_LATLON.kml"
        if png.exists() and kml.exists():
            grouped.setdefault((g["group"], g["product"]), []).append((g, png, kml))
    layers = []
    for (group, product), items in grouped.items():
        sources = []
        for g, png, kml in items:
            rel = f"tiles/previews/{group}/{product.lower()}/f{g['frame']:03d}"
            t = build_source(png, kml, public / rel, zmin, zmax)
            sources.append({"frame": g["frame"], "granule": g["file_id"], "sourceFilename": png.name, "bounds": t["bounds"],
                            "tiles": {"url": f"{public.name}/{rel}/{{z}}/{{x}}/{{y}}.png", "minzoom": zmin, "maxzoom": zmax, "count": t["count"]}})
        g = items[0][0]
        layers.append({"id": f"preview:{group}:{product.lower()}", "groupId": group, "name": f"{product} browse preview", "category": "preview", "previewOf": CATEGORY[product],
                       "mission": "NISAR", "instrument": "L-SAR", "productType": product, "measurementClass": "derived", "measurementType": "preview", "kind": "continuous", "units": None,
                       "acquisition": {"reference": g["ref_date"], "secondary": g.get("sec_date")}, "orbitDirection": g["direction"], "track": g["track"], "frames": [i[0]["frame"] for i in items],
                       "qualityLayerIds": [], "status": "renderable", "statusReason": None, "sources": sources, "productMaturity": f"Provisional per catalogue ({cfg['crid']})",
                       "sourceGranules": [i[0]["file_id"] for i in items], "attribution": "NASA/JPL-Caltech/ISRO, NISAR; distributed by ASF DAAC", "limitations": LIMITS})
    return layers
