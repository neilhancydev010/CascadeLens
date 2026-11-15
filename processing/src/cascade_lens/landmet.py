"""LANDMET L3 as a second case study: a test of the product on a dataset it was never designed for.

Global land meteorology, one day, 8 three-hourly steps, on a roughly 1 degree equal-area grid. Not radar, not NISAR, not Rasuwa.
Per-file metadata here is unreliable, so nothing is taken on trust:
- some variables use `scale`, others `scale_factor`, and some valid ranges are swapped, so each variable names its own key
- many variables are entirely fill, so emptiness is detected and shown rather than assumed
- some values are physically impossible, so plausible limits classify them as masked without changing them
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

import h5py
import numpy as np
from rasterio.transform import from_origin

from . import export, quality

TRANSFORM = from_origin(-180, 90, 1, 1)  # 1 degree raster of the equal-area cells. A cell may span several pixels, all with its value
ENVELOPE = [-180.0, -60.0, 180.0, 80.0]
ZOOM = (0, 3)
ATTRIBUTION = "W. B. Rossow, City College of New York NOAA/CREST. LANDMET L3 v1, DOI 10.5067/MEASURES/LANDMET/DATA001"
LIMITS = ["A test dataset. It is not NISAR data and says nothing about the 2026 Rasuwa event: it is from 2007.",
          "Cells are about 110 km across, so one cell can blend very different terrain, especially in mountains."]


def _v(id_, var, name, units, colormap, what, measures, inspect, establishes, scale="scale_factor", plausible=None, fixed=None, source="", limits=()):
    return dict(id=id_, var=var, name=name, units=units, colormap=colormap, scale=scale, plausible=plausible, fixed=fixed, source=source, limits=list(limits),
                explanation=dict(what=what, measures=measures, inspect=inspect, establishes=establishes))


VARIABLES = [
    _v("skin-temp", "FDtemps", "Land surface skin temperature", "K", "diverging", "How hot the ground surface was, from the ISCCP FD satellite product.", "Temperature of the surface itself, in kelvin. It swings far more than air temperature.",
       "Move through the day: the warm peak should travel from east to west with local noon.", "Surface temperature only, at about 110 km scale.", source="ISCCP FD"),
    _v("air-temp", "NNta", "Near-surface air temperature", "K", "diverging", "Air temperature about 2 m above ground, retrieved from satellite sounders (ISCCP NNHIRS).", "Air temperature in kelvin.",
       "Compare it with skin temperature, and with the station temperature layer.", "A satellite retrieval at about 110 km scale, not a station reading.", source="ISCCP NNHIRS"),
    _v("station-temp", "ISDta", "Station air temperature", "K", "diverging", "Air temperature from ground stations (Integrated Surface Database), gridded to the cells.", "Air temperature in kelvin.",
       "Compare it with the satellite air temperature. Sparse regions rely on filled values.", "A gridded station product. Many cells hold filled rather than observed values.", source="ISD stations", limits=["Cells without nearby stations hold filled values."]),
    _v("pressure", "psurf", "Surface pressure", "hPa", "sequential", "Atmospheric pressure at the land surface (ISCCP NNHIRS).", "Pressure in hectopascals. It mostly follows terrain height.",
       "High ground shows clearly as low pressure.", "Mostly a map of elevation in this one-day view.", source="ISCCP NNHIRS"),
    _v("humidity", "NNrha", "Near-surface relative humidity", "percent", "sequential", "Relative humidity near the surface, retrieved from satellite sounders (ISCCP NNHIRS).", "Relative humidity as a percentage.",
       "Values over 100 percent are retrieval artefacts, and are flagged as masked.", "A satellite retrieval. It is not a station measurement.", plausible=(0, 100.5), source="ISCCP NNHIRS", limits=["The file allows values up to 150 percent. Those over 100 are flagged as masked."]),
    _v("wind", "ISDwspeed", "Station wind speed", "m/s", "sequential", "Wind speed from ground stations (Integrated Surface Database).", "Wind speed in metres per second.",
       "Check any extreme value: station records contain errors.", "A gridded station product, sparse in many regions.", plausible=(0, 60), source="ISD stations", limits=["The file contains values up to 118.6 m/s. Anything above 60 m/s is treated as implausible and flagged as masked."]),
    _v("precip", "preciprate", "Precipitation rate", "mm/hour", "rain", "Rain and snow rate from the merged TMPA and GPCP satellite records.", "Precipitation in millimetres per hour.",
       "Most cells are dry on any given step.", "Satellite precipitation at about 110 km scale.", source="TMPA and GPCP"),
    _v("snow", "snowfrac", "Snow cover fraction", "1", "sequential", "The share of each cell covered by snow, for the whole day.", "Fraction of the cell, from 0 to 1.",
       "Late December: the northern continents should be largely covered.", "Snow cover only, for one day.", fixed=(0.0, 1.0), source="LANDMET"),
    _v("soil-moisture", "vsm", "Soil moisture", "m3/m3", "sequential", "Water held in the top soil layer, from satellite retrievals, for the whole day.", "Volumetric soil moisture.",
       "Frozen and snow-covered ground usually has no retrieval.", "Top-layer soil moisture only, with large gaps.", source="LANDMET"),
    _v("flood", "floodfrac", "Temporary flood fraction", "1", "rain", "The share of each cell temporarily flooded, for the whole day.", "Fraction of the cell, from 0 to 1.",
       "Look along major river basins.", "A coarse estimate. It has nothing to do with the Rasuwa flood.", scale="scale", fixed=(0.0, 0.5), source="Papa et al."),
    _v("height", "height", "Mean terrain height", "m", "terrain", "Mean height of each cell, from ISCCP topography.", "Height above sea level in metres.",
       "Note how much the Himalaya is smoothed at this scale.", "Cell averages, far coarser than the 30 m terrain in the Rasuwa case.", scale=None, fixed=(0.0, 5500.0), source="ISCCP"),
]
EMPTY_CANDIDATES = [("FDta", "Air temperature (ISCCP FD)"), ("totclfrac", "Total cloud fraction"), ("dccfrac", "Deep convective cloud fraction"), ("swsurfflux", "Net shortwave surface flux"),
                    ("lwsurfflux", "Net longwave surface flux"), ("ET_tran_liquid", "Transpiration"), ("ET_soil_liquid", "Soil evaporation")]
BOOKMARKS = [("himalaya", "Himalaya and Nepal", [70.0, 20.0, 100.0, 38.0], (85.3, 28.2), "Rasuwa area, one coarse cell"), ("sahara", "Sahara", [-20.0, 12.0, 40.0, 34.0], (10.5, 23.5), "Central Sahara"),
             ("siberia", "Siberia", [80.0, 45.0, 140.0, 72.0], (110.0, 62.0), "Central Siberia"), ("australia", "Central Australia", [110.0, -40.0, 155.0, -10.0], (134.5, -25.5), "Central Australia")]


def cell_grid(zones: np.ndarray) -> np.ndarray:
    """Cell index for every 1 degree pixel: row 0 is the northern edge, column 0 is 180 W. Zone 1 is the southernmost, longitudes start at 0 E."""
    starts = np.r_[0, np.cumsum(zones)[:-1]]
    grid = np.zeros((180, 360), np.int32)
    centres = np.arange(360) + 0.5
    for z, n in enumerate(zones):
        grid[179 - z] = np.roll(starts[z] + (centres / 360 * n).astype(np.int32), 180)
    return grid


def read_cells(ds, spec: dict, step: int | None) -> np.ndarray:
    raw = ds[step] if step is not None else ds[()]
    fill = ds.attrs.get("_FillValue")
    out = raw.astype(np.float32)
    if spec["scale"]:
        out *= float(ds.attrs[spec["scale"]][0])
    if fill is not None:
        out[raw == fill[0]] = np.nan
    return out


def classify(values: np.ndarray, plausible) -> np.ndarray:
    v = np.full(values.shape, quality.VALID, np.uint8)
    if plausible:
        with np.errstate(invalid="ignore"):
            v[(values < plausible[0]) | (values > plausible[1])] = quality.MASKED
    v[~np.isfinite(values)] = quality.NODATA
    return v


def diurnal_peak_local_hour(temp: np.ndarray, lat: np.ndarray, lon: np.ndarray, utc: np.ndarray) -> float:
    """Median local solar hour of the daily temperature peak over low-latitude land. It should be early afternoon if time and longitude are both right."""
    ok = np.isfinite(temp).all(axis=0) & (np.abs(lat) < 40)
    peak = utc[np.argmax(temp[:, ok], axis=0)]
    local = (peak + lon[ok] / 15) % 24
    return float(np.median(local))


def _layer(spec, sources, steps, stats, stops, status="sampleable", reason=None, valid=None):
    unit = "" if spec["units"] == "1" else spec["units"]
    return {"id": f"landmet:{spec['id']}", "groupId": None, "name": spec["name"], "category": "gridded", "mission": "LANDMET", "instrument": spec["source"] or "Multiple sources", "productType": "L3 v1", "measurementClass": "derived",
            "measurementType": "gridded", "kind": "continuous", "units": spec["units"], "acquisition": {"reference": "2007-12-31", "secondary": None}, "orbitDirection": None, "track": None, "frames": [], "postingM": [111000, 111000],
            "crs": "EPSG:4326", "qualityLayerIds": [], "status": status, "statusReason": reason, "sources": sources, "timeSteps": steps, "stats": stats, "explanation": spec["explanation"], "validPct": valid,
            "legend": {"type": "continuous", "stops": stops, "min": stats.get("displayMin"), "max": stats.get("displayMax"), "unit": unit} if stats else None, "productMaturity": "Version 1, CCNY, November 2016", "sourceGranules": [],
            "attribution": ATTRIBUTION, "limitations": LIMITS + spec["limits"]}


def prepare(nc_path, public: pathlib.Path, work: pathlib.Path, qa_dir: pathlib.Path) -> dict:
    """Returns the manifest for this case. Writes COGs and tiles under public/ and a QA report under qa_dir/."""
    public, work, qa_dir = pathlib.Path(public), pathlib.Path(work), pathlib.Path(qa_dir)
    zmin, zmax = ZOOM
    layers, qa = [], {"file": pathlib.Path(nc_path).name, "variables": {}}
    with h5py.File(nc_path, "r") as f:
        qa["sha256"] = export.sha256(nc_path)
        lat, lon, utc = f["eqlat"][()], f["eqlon"][()], f["utctime"][()].astype(float)
        grid = cell_grid(f["eqcells_in_zone"][()])
        centre = ((lon + 180) % 360) - 180
        for spec in VARIABLES:
            ds = f[spec["var"]]
            timed = ds.ndim == 2
            steps = list(range(ds.shape[0])) if timed else [None]
            cells = [read_cells(ds, spec, s) for s in steps]
            everything = np.stack(cells)
            if not np.isfinite(everything).any():
                layers.append(_layer(spec, [], None, None, None, "unavailable", "Every value in this file is fill."))
                continue
            cls = [classify(c, spec["plausible"]) for c in cells]
            shown = everything[np.stack(cls) == quality.VALID]
            stats = export.statistics(shown, fixed=spec["fixed"])
            stops = export.COLORMAPS[spec["colormap"]]
            step_records = []
            for k, (c, v) in enumerate(zip(cells, cls)):
                tag = f"t{k:02d}"
                tif = export.write_geotiff(work / spec["id"] / f"{tag}.tif", c[grid], TRANSFORM, 4326, tags={"SOURCE_VARIABLE": spec["var"], "SOURCE_FILE": pathlib.Path(nc_path).name})
                vtif = export.write_geotiff(work / spec["id"] / f"{tag}.validity.tif", v[grid], TRANSFORM, 4326, nodata=255)
                cog = export.to_cog(tif, public / "sampling/landmet" / f"{spec['id']}_{tag}.tif")
                vcog = export.to_cog(vtif, public / "sampling/landmet" / f"{spec['id']}_{tag}_validity.tif")
                warped, x0, y0 = export.warp_to_tile_grid(tif, zmax, validity_path=vtif)
                folder = public / "tiles/landmet" / spec["id"] / tag
                n = export.write_pyramid(export.colorize(warped, stops, stats["displayMin"], stats["displayMax"]), x0, y0, zmax, zmin, folder)
                rel = lambda p: pathlib.Path(p).relative_to(public.parent).as_posix()  # noqa: E731
                source = {"frame": None, "granule": pathlib.Path(nc_path).name, "sourceFilename": pathlib.Path(nc_path).name, "sourceDataset": spec["var"], "bounds": [-180.0, -85.0, 180.0, 85.0], "sampling": rel(cog), "validity": rel(vcog),
                          "validFraction": float((v == quality.VALID).mean()), "maskedFraction": float((v == quality.MASKED).mean()), "tiles": {"url": f"{rel(folder)}/{{z}}/{{x}}/{{y}}.png", "minzoom": zmin, "maxzoom": zmax, "count": n}}
                step_records.append({"label": f"{int(utc[k]):02d}:00 UTC" if timed else "Whole day", "sources": [source]})
            all_cls = np.stack(cls)
            qa["variables"][spec["var"]] = {"name": spec["name"], "validCells": int((all_cls == quality.VALID).sum()), "maskedCells": int((all_cls == quality.MASKED).sum()), "min": float(np.nanmin(everything)), "max": float(np.nanmax(everything))}
            layers.append(_layer(spec, step_records[0]["sources"], step_records if timed else None, stats, stops))
        for var, name in EMPTY_CANDIDATES:
            ds = f[var]
            empty = bool((ds[()] == ds.attrs["_FillValue"][0]).all())
            qa["variables"][var] = {"name": name, "empty": empty}
            if empty:
                spec = _v(var, var, name, "1", "sequential", "", "", "", "")
                layers.append(_layer(spec, [], None, None, None, "unavailable", "Every value in this file is fill."))
        skin = read_cells(f["FDtemps"], VARIABLES[0], None).astype(float)
        qa["diurnalPeakLocalHour"] = round(diurnal_peak_local_hour(skin, lat, centre, utc), 2)
        land = read_cells(f["land_fraction"], dict(scale="scale"), None)
    tif = export.write_geotiff(work / "land" / "t00.tif", land[grid], TRANSFORM, 4326)
    vtif = export.write_geotiff(work / "land" / "t00.validity.tif", classify(land, None)[grid], TRANSFORM, 4326, nodata=255)
    cog, vcog = export.to_cog(tif, public / "sampling/landmet/land.tif"), export.to_cog(vtif, public / "sampling/landmet/land_validity.tif")
    warped, x0, y0 = export.warp_to_tile_grid(tif, zmax)
    n = export.write_pyramid(export.colorize(warped, export.COLORMAPS["land"], 0, 1), x0, y0, zmax, zmin, public / "tiles/landmet/land")
    base = _layer(_v("land", "land_fraction", "Land fraction", "1", "land", "The share of each cell that is land. It is the background map for this case.", "Fraction of the cell, from 0 to 1.", "Use it to find your way around.", "Geography only.", source="ISCCP"), [], None, None, None)
    base |= {"id": "context:terrain", "category": "terrain", "status": "sampleable", "legend": {"type": "continuous", "stops": export.COLORMAPS["land"], "min": 0, "max": 1, "unit": ""},
             "sources": [{"frame": None, "granule": pathlib.Path(nc_path).name, "sourceFilename": pathlib.Path(nc_path).name, "bounds": [-180.0, -85.0, 180.0, 85.0], "sampling": cog.relative_to(public.parent).as_posix(), "validity": vcog.relative_to(public.parent).as_posix(),
                          "tiles": {"url": "data/tiles/landmet/land/{z}/{x}/{y}.png", "minzoom": zmin, "maxzoom": zmax, "count": n}}]}
    qa_dir.mkdir(parents=True, exist_ok=True)
    (qa_dir / "landmet-report.json").write_text(json.dumps(qa, indent=1), encoding="utf-8")
    return {"schemaVersion": 1, "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fixture": True,
            "fixtureLabel": "TEST DATASET. LANDMET global land meteorology, 31 December 2007. This is not NISAR data and says nothing about the 2026 Rasuwa event.",
            "caseStudy": {"id": "landmet-2007", "name": "LANDMET global land meteorology", "eventDate": "2007-12-31", "searchEnvelope": ENVELOPE},
            "bookmarks": [{"id": i, "name": n, "bounds": b, "anchor": {"lng": a[0], "lat": a[1], "label": l}, "basis": "Navigation frame for exploring the test dataset."} for i, n, b, a, l in BOOKMARKS],
            "groups": [], "granules": [], "layers": [base, *sorted(layers, key=lambda x: x["status"] != "sampleable")], "qa": qa}
