"""prepare_simulation must work for a new event with nothing but rivers, terrain and a start point."""
import importlib.util
import json
import pathlib

import numpy as np
import rasterio
from rasterio.transform import from_origin

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("prepare_simulation", ROOT / "processing/scripts/prepare_simulation.py")
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)


def geojson(path, *features):
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf8")


def feature(kind, coordinates, **properties):
    return {"type": "Feature", "properties": properties, "geometry": {"type": kind, "coordinates": coordinates}}


def test_builds_a_simulation_for_an_unrelated_place(tmp_path):
    # A valley running east to west in Peru, falling 1000 m to 100 m, with a dry side branch.
    dem = np.tile(np.linspace(100, 1000, 300), (100, 1)).astype("float32")
    with rasterio.open(tmp_path / "dem.tif", "w", driver="GTiff", width=300, height=100, count=1, dtype="float32", crs="EPSG:4326", transform=from_origin(-78, -9, 0.001, 0.001)) as f:
        f.write(dem, 1)
    geojson(tmp_path / "rivers.geojson",
            feature("LineString", [[-77.72, -9.05], [-77.85, -9.05]], name="Rio Test"),
            feature("LineString", [[-77.85, -9.05], [-77.99, -9.05]], name="Rio Test"),
            feature("LineString", [[-77.85, -9.05], [-77.85, -9.09]]))
    geojson(tmp_path / "homes.geojson", feature("Point", [-77.9, -9.051]), feature("Point", [-77.9, -8.9]))
    geojson(tmp_path / "towns.geojson", feature("Point", [-77.8, -9.05], name="Pueblo"))
    cfg = {"dem": "dem.tif", "rivers": "rivers.geojson", "start": [-77.71, -9.05], "buildings": "homes.geojson", "places": "towns.geojson"}
    out = sim.build(cfg, tmp_path)
    assert out["path"][0][:2] == [-77.71, -9.05]
    assert 30 < len(out["path"]) < 34  # About 0.28 degrees of longitude at this latitude
    assert out["path"][-1][0] < -77.97  # It ran down the valley, not up the side branch
    levels = [p[2] for p in out["path"]]
    assert all(a >= b for a, b in zip(levels, levels[1:]))
    assert out["totals"]["buildings"] == 1 and out["totals"]["buildingsAll"] == 2  # The far building is in another valley
    assert [p["name"] for p in out["places"]] == ["Pueblo"]
    assert out["totals"]["roadKm"] == 0
