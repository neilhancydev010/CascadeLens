"""GeoTIFF/COG writing, statistics and XYZ PNG tile pyramids. Tiles are display only; COGs keep the measured values."""
from __future__ import annotations

import hashlib
import math
import pathlib

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.shutil import copy as rio_copy
from rasterio.warp import reproject, transform_bounds

from .quality import VALID

R = 6378137.0
LAT_LIMIT = 85.0511
ORIGIN = math.pi * R
COLORMAPS = {  # shared with the legend through the manifest, so tiles and legend cannot disagree
    "diverging": ["#2166ac", "#67a9cf", "#f7f7f7", "#ef8a62", "#b2182b"],
    "sequential": ["#000004", "#51127c", "#b73779", "#fc8961", "#fcfdbf"],
    "grey": ["#0b0b0b", "#f2f2f2"],
    "terrain": ["#31543b", "#6f8a4f", "#c9b98a", "#a08570", "#ffffff"],
    "categorical": ["#4e79a7", "#f28e2b", "#59a14f", "#b07aa1", "#edc948", "#76b7b2", "#e15759", "#9c755f"],
    "validity": ["#00000000", "#00000000", "#ff00d4"],
    "rain": ["#eff3ff", "#6baed6", "#08306b"],
    "land": ["#0f1518", "#3e4c52"],
}


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(1 << 22):
            h.update(b)
    return h.hexdigest()


def write_geotiff(path, arr: np.ndarray, transform, epsg: int, nodata=None, tags: dict | None = None):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if nodata is None and np.issubdtype(arr.dtype, np.floating):
        nodata = float("nan")
    with rasterio.open(path, "w", driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1, dtype=arr.dtype.name,
                       crs=f"EPSG:{epsg}", transform=transform, nodata=nodata, compress="deflate", tiled=True) as d:
        d.write(arr, 1)
        if tags:
            d.update_tags(**{k: str(v) for k, v in tags.items()})
    return path


def to_cog(src, dst):
    """Native-grid cloud-optimised copy for browser range reads. Nearest overviews: no invented values."""
    dst = pathlib.Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    rio_copy(str(src), str(dst), driver="COG", compress="DEFLATE", blocksize=256, overview_resampling="nearest")
    return dst


def statistics(a: np.ndarray, symmetric=False, fixed: tuple | None = None, bins=40) -> dict:
    v = a[np.isfinite(a)]
    if not v.size:
        return {"count": 0}
    p2, p98 = (float(x) for x in np.percentile(v, [2, 98]))
    lo, hi = fixed or (p2, p98)
    if symmetric and not fixed:
        m = np.median(v)
        h = float(max(abs(p2 - m), abs(p98 - m)))
        lo, hi = float(m - h), float(m + h)
    if hi <= lo:
        hi = lo + 1
    counts, edges = np.histogram(v, bins=bins, range=(lo, hi))
    return {"count": int(v.size), "min": float(v.min()), "max": float(v.max()), "mean": float(v.mean()), "median": float(np.median(v)),
            "p2": p2, "p98": p98, "displayMin": lo, "displayMax": hi, "histogram": {"edges": [round(float(e), 5) for e in edges], "counts": counts.tolist()}}


def _hex(c: str) -> tuple:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in range(0, len(c), 2)) + ((255,) if len(c) == 6 else ())


def colorize(a: np.ndarray, stops: list[str], lo: float, hi: float) -> np.ndarray:
    """Continuous ramp; NaN becomes fully transparent."""
    t = np.clip((a - lo) / (hi - lo), 0, 1)
    pts = np.linspace(0, 1, len(stops))
    rgba = np.zeros(a.shape + (4,), np.uint8)
    for i in range(3):
        rgba[..., i] = np.interp(np.nan_to_num(t), pts, [_hex(s)[i] for s in stops])
    rgba[..., 3] = np.where(np.isfinite(a), 255, 0)
    return rgba


def colorize_categorical(a: np.ndarray, stops: list[str]) -> np.ndarray:
    """Integer classes cycle through the palette; label numbers carry no order."""
    table = np.array([_hex(s) for s in stops], np.uint8)
    rgba = table[np.nan_to_num(a).astype(np.int64) % len(table)]
    rgba[~np.isfinite(a)] = 0
    return rgba


def colorize_index(a: np.ndarray, stops: list[str]) -> np.ndarray:
    """Direct class -> colour lookup, used for validity overlays."""
    table = np.array([_hex(s) for s in stops], np.uint8)
    return table[a.astype(np.int64)]


def tile_range(bbox, z: int) -> tuple[int, int, int, int]:
    """Inclusive XYZ tile range for a lon/lat bbox (y grows southward, not TMS)."""
    w, s, e, n = bbox
    s, n = max(s, -LAT_LIMIT), min(n, LAT_LIMIT)  # Web Mercator stops here, and global rasters reach the poles

    def tx(lon):
        return min(int((lon + 180) / 360 * 2 ** z), 2 ** z - 1)

    def ty(lat):
        r = math.radians(lat)
        return int((1 - math.asinh(math.tan(r)) / math.pi) / 2 * 2 ** z)

    return tx(w), ty(n), tx(e), ty(s)


def _mercator_transform(x0: int, y0: int, z: int):
    res = 2 * ORIGIN / (256 * 2 ** z)
    return rasterio.Affine(res, 0, -ORIGIN + x0 * 256 * res, 0, -res, ORIGIN - y0 * 256 * res)


def warp_to_tile_grid(src_path, zmax: int, resampling=Resampling.nearest, validity_path=None) -> tuple[np.ndarray, int, int]:
    """Warp a raster onto the zmax tile grid. Pixels whose validity class is not VALID become NaN."""
    with rasterio.open(src_path) as src:
        bbox = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
        x0, y0, x1, y1 = tile_range(bbox, zmax)
        h, w = (y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256
        dst = np.full((h, w), np.nan, np.float32)
        tr = _mercator_transform(x0, y0, zmax)
        reproject(rasterio.band(src, 1), dst, dst_transform=tr, dst_crs="EPSG:3857", dst_nodata=np.nan, resampling=resampling)
    if validity_path:
        dst[warp_classes(validity_path, tr, (h, w)) != VALID] = np.nan
    return dst, x0, y0


def warp_classes(path, transform, shape) -> np.ndarray:
    """Warp a validity raster. Its nodata must stay 255: with a destination nodata of 0, GDAL rewrites class 0 to 1,
    which turns no-data pixels into valid ones."""
    cls = np.full(shape, 255, np.uint8)
    with rasterio.open(path) as v:
        reproject(rasterio.band(v, 1), cls, dst_transform=transform, dst_crs="EPSG:3857", src_nodata=255, dst_nodata=255, resampling=Resampling.nearest)
    cls[cls == 255] = 0
    return cls


def warp_rgba(bands: np.ndarray, transform, crs, bbox, zmax: int) -> tuple[np.ndarray, int, int]:
    """Warp an already-coloured 4-band image onto the zmax tile grid covering bbox, for layers that hold no measurements."""
    x0, y0, x1, y1 = tile_range(bbox, zmax)
    dst = np.zeros((4, (y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256), np.uint8)
    reproject(bands, dst, src_transform=transform, src_crs=crs, dst_transform=_mercator_transform(x0, y0, zmax), dst_crs="EPSG:3857", resampling=Resampling.nearest)
    return np.moveaxis(dst, 0, -1), x0, y0


def write_pyramid(rgba: np.ndarray, x0: int, y0: int, zmax: int, zmin: int, out_dir, smooth=False) -> int:
    """Slice into 256 px PNGs, halving per zoom. Decimation by default so measurement tiles show only real pixel values."""
    out_dir = pathlib.Path(out_dir)
    n = 0
    for z in range(zmax, zmin - 1, -1):
        h, w = rgba.shape[:2]
        for r in range(0, h, 256):
            for c in range(0, w, 256):
                t = rgba[r:r + 256, c:c + 256]
                if not t[..., 3].any():
                    continue  # MapLibre treats a missing tile as empty; 404s here are expected and harmless
                p = out_dir / str(z) / str(x0 + c // 256) / f"{y0 + r // 256}.png"
                p.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(t, "RGBA").save(p, optimize=False, compress_level=9)
                n += 1
        if z == zmin:
            break
        pad_t, pad_l = (256 if y0 % 2 else 0), (256 if x0 % 2 else 0)
        pad_b, pad_r = ((h + pad_t) % 512), ((w + pad_l) % 512)
        rgba = np.pad(rgba, ((pad_t, pad_b), (pad_l, pad_r), (0, 0)))
        y0, x0 = (y0 - (1 if y0 % 2 else 0)) // 2, (x0 - (1 if x0 % 2 else 0)) // 2
        if smooth:
            b = rgba.reshape(rgba.shape[0] // 2, 2, rgba.shape[1] // 2, 2, 4).astype(np.uint16)
            rgba = (b.sum(axis=(1, 3)) // 4).astype(np.uint8)
        else:
            rgba = rgba[::2, ::2]
    return n
