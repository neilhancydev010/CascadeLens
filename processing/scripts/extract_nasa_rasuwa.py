"""Cut the Rasuwa window out of the NASA downloads and shrink it to 40 m grids the app can use.

usage: python -I extract_nasa_rasuwa.py FOLDER_WITH_NASA_DOWNLOADS
Reads NASADEM_HGT_*.zip, NISAR_L2_PR_GCOV_*.h5 and OPERA_L2_RTC-S1_*_VV.tif / _mask.tif from that folder (never changes them)
and writes data/processed/nasa/ (git-ignored):
  nasadem.tif                       NASADEM heights, EPSG:4326 at the source 1 arc-second posting, clipped to the case envelope
  gcov_<date>_t<track>_hh.tif       NISAR GCOV gamma-0 HH, linear power, mean of the valid 10/20 m samples in each 40 m cell, UTM 45N
  gcov_<date>_t<track>_hh.json      the file's own identification (granule, DOI, release, pass, mode)
  opera_<date>_t<relorbit>_vv.tif   OPERA RTC-S1 gamma-0 VV, bursts of one pass merged, same 40 m UTM 45N grid
Every value is the source's own measurement averaged; nothing is classified here.
"""
import json
import pathlib
import re
import sys
import zipfile
from collections import defaultdict

import h5py
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

ROOT = pathlib.Path(__file__).resolve().parents[2]
CFG = json.loads((ROOT / "processing/configs/pipeline.json").read_text())
WEST, SOUTH, EAST, NORTH = CFG["aoi_bbox"]
OUT = ROOT / "data/processed/nasa"
CRS = "EPSG:32645"
CELL = 40.0
SRC = pathlib.Path(sys.argv[1]).expanduser()
OUT.mkdir(parents=True, exist_ok=True)


def utm_box(epsg, pad=200.0):
    t = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    lon = np.r_[np.linspace(WEST, EAST, 50), np.full(50, EAST), np.linspace(EAST, WEST, 50), np.full(50, WEST)]
    lat = np.r_[np.full(50, SOUTH), np.linspace(SOUTH, NORTH, 50), np.full(50, NORTH), np.linspace(NORTH, SOUTH, 50)]
    x, y = t.transform(lon, lat)
    return min(x) - pad, min(y) - pad, max(x) + pad, max(y) + pad


# The common 40 m grid: the envelope's outer box in UTM 45N, snapped to 40 m
bx0, by0, bx1, by1 = utm_box(32645)
GX0, GY1 = np.floor(bx0 / CELL) * CELL, np.ceil(by1 / CELL) * CELL
GW, GH = int(np.ceil((bx1 - GX0) / CELL)), int(np.ceil((GY1 - by0) / CELL))
GRID_TF = from_origin(GX0, GY1, CELL, CELL)


def save(path, arr, tf=GRID_TF, crs=CRS, tags=None):
    with rasterio.open(path, "w", driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1, dtype="float32", crs=crs, transform=tf,
                       nodata=np.nan, compress="deflate", predictor=3, tiled=True) as d:
        d.write(arr.astype("float32"), 1)
        if tags:
            d.update_tags(**{k: str(v) for k, v in tags.items()})


def nasadem():
    zips = sorted(SRC.glob("NASADEM_HGT_*.zip"))
    mems, srcs = [], []
    for z in zips:
        tile = re.search(r"NASADEM_HGT_(\w+)\.zip", z.name).group(1)
        raw = zipfile.ZipFile(z).read(f"{tile}.hgt")
        lat = int(tile[1:3]) * (1 if tile[0] == "n" else -1)
        lon = int(tile[4:7]) * (1 if tile[3] == "e" else -1)
        a = np.frombuffer(raw, ">i2").reshape(3601, 3601).astype("float32")
        a[a == -32768] = np.nan
        m = MemoryFile()
        d = m.open(driver="GTiff", width=3601, height=3601, count=1, dtype="float32", crs="EPSG:4326", nodata=np.nan,
                   transform=from_origin(lon - 0.5 / 3600, lat + 1 + 0.5 / 3600, 1 / 3600, 1 / 3600))
        d.write(a, 1)
        mems.append(m)
        srcs.append(d)
    arr, tf = merge(srcs, bounds=(WEST, SOUTH, EAST, NORTH), nodata=np.nan, dtype="float32", resampling=Resampling.nearest)
    save(OUT / "nasadem.tif", arr[0], tf, "EPSG:4326", {"SOURCE": "NASADEM_HGT v001", "TILES": ",".join(z.name for z in zips)})
    print(f"nasadem: {arr[0].shape}, {np.isfinite(arr[0]).mean():.4f} valid, {np.nanmin(arr[0]):.0f}..{np.nanmax(arr[0]):.0f} m")


def text(v):
    v = v[()]
    return v.decode() if isinstance(v, bytes) else (v.item() if hasattr(v, "item") else v)


def gcov(path):
    f = h5py.File(path, "r")
    idn = f["science/LSAR/identification"]
    g = f["science/LSAR/GCOV/grids/frequencyA"]
    epsg = int(g["projection"][()])
    xs, ys, dx = g["xCoordinates"][:], g["yCoordinates"][:], float(g["xCoordinateSpacing"][()])
    x0, y0, x1, y1 = utm_box(epsg, pad=2000)
    c0, c1 = np.searchsorted(xs, x0), np.searchsorted(xs, x1)
    r0, r1 = np.searchsorted(-ys, -y1), np.searchsorted(-ys, -y0)
    k = int(round(CELL / dx)) if epsg == 32645 else 1
    # Whole 40 m blocks on the common grid when the file is already UTM 45N; otherwise keep the source posting and warp below
    hh = g["HHHH"][r0:r1, c0:c1]
    mask = g["mask"][r0:r1, c0:c1]
    hh = np.where((mask > 0) & (mask < 255) & np.isfinite(hh) & (hh > 0), hh, np.nan)
    h, w = (hh.shape[0] // k) * k, (hh.shape[1] // k) * k
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore", RuntimeWarning)
        blk = np.nanmean(hh[:h, :w].reshape(h // k, k, w // k, k), axis=(1, 3))
    tf = from_origin(xs[c0] - dx / 2, ys[r0] + dx / 2, dx * k, dx * k)
    out = np.full((GH, GW), np.nan, "float32")
    reproject(blk, out, src_transform=tf, src_crs=f"EPSG:{epsg}", src_nodata=np.nan, dst_transform=GRID_TF, dst_crs=CRS, dst_nodata=np.nan,
              resampling=Resampling.average)
    date = text(idn["zeroDopplerStartTime"])[:10]
    track = int(text(idn["trackNumber"]))
    meta = {"granule": text(idn["granuleId"]) if "granuleId" in idn else path.stem, "sourceFilename": path.name, "date": date, "track": track,
            "frame": int(text(idn["frameNumber"])), "orbit": text(idn["orbitPassDirection"]).upper(), "doi": text(idn["productDoi"]),
            "release": text(idn["compositeReleaseId"]), "urgent": text(idn["isUrgentObservation"]) == "True", "sourceEpsg": epsg, "sourcePostingM": dx,
            "covarianceTerms": [s.decode() for s in g["listOfCovarianceTerms"][()]], "dataset": "/science/LSAR/GCOV/grids/frequencyA/HHHH",
            "modeBandwidthMHz": int(re.search(r"_(\d{2})05_", path.name).group(1)), "validFraction": float(np.isfinite(out).mean())}
    stem = f"gcov_{date.replace('-', '')}_t{track:03d}_hh"
    save(OUT / f"{stem}.tif", out, tags={"SOURCE": path.name, "DATASET": meta["dataset"]})
    (OUT / f"{stem}.json").write_text(json.dumps(meta, indent=1))
    print(f"{stem}: {meta['validFraction']:.3f} of the case grid has data")


def opera():
    groups = defaultdict(list)
    for p in sorted(SRC.glob("OPERA_L2_RTC-S1_*_VV.tif")):
        m = re.match(r"OPERA_L2_RTC-S1_T(\d{3})-\d+-IW\d_(\d{8})T", p.name)
        groups[(m.group(2), m.group(1))].append(p)
    for (date, rel), files in sorted(groups.items()):
        acc, cnt = np.zeros((GH, GW)), np.zeros((GH, GW))
        for p in files:
            mpath = p.with_name(p.name.replace("_VV.tif", "_mask.tif"))
            with rasterio.open(p) as s:
                a = s.read(1).astype("float32")
                if mpath.exists():
                    with rasterio.open(mpath) as ms:
                        a = np.where(ms.read(1) == 0, a, np.nan)  # OPERA mask: 0 is clear; layover, shadow and fill are not
                a = np.where(np.isfinite(a) & (a > 0), a, np.nan)
                o = np.full((GH, GW), np.nan, "float32")
                reproject(a, o, src_transform=s.transform, src_crs=s.crs, src_nodata=np.nan, dst_transform=GRID_TF, dst_crs=CRS, dst_nodata=np.nan, resampling=Resampling.average)
            ok = np.isfinite(o)
            acc[ok] += o[ok]
            cnt[ok] += 1
        out = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan).astype("float32")
        save(OUT / f"opera_{date}_t{rel}_vv.tif", out, tags={"SOURCE": ",".join(p.name for p in files)})
        print(f"opera {date} T{rel}: {len(files)} bursts, {np.isfinite(out).mean():.3f} of the case grid")


if __name__ == "__main__":
    what = sys.argv[2:] or ["dem", "gcov", "opera"]
    print(f"grid {GW}x{GH} at {CELL:.0f} m, origin {GX0:.0f},{GY1:.0f}")
    if "dem" in what:
        nasadem()
    if "gcov" in what:
        for p in sorted(SRC.glob("NISAR_L2_PR_GCOV_*.h5")):
            gcov(p)
    if "opera" in what:
        opera()
