import numpy as np

from cascade_lens import hazard as hz


def test_slope_of_a_known_plane():
    y, x = np.mgrid[0:20, 0:20].astype(float)
    z = x * 40 * np.tan(np.radians(30))  # 30 deg ramp at 40 m posting
    assert abs(np.median(hz.slope_deg(z, 40)) - 30) < 0.01


def test_flow_accumulates_down_a_ramp():
    y, x = np.mgrid[0:5, 0:6].astype(float)
    acc = hz.flow_accumulation(100 - x * 10)  # everything drains to x = 5
    assert acc[:, 0].max() == 1
    assert acc[:, -1].min() >= 6


def test_hollow_is_convergent():
    y, x = np.mgrid[-15:16, -15:16].astype(float)
    valley = 0.5 * x ** 2 - 20 * y  # slope downhill in +y, valley along x = 0
    k = hz.plan_curvature(valley, 40)
    assert k[15, 15] < 0


def test_classes_follow_the_rules():
    f = np.array([0, hz.STEEP_1, hz.STEEP_1 | hz.HOLLOW, hz.STEEP_2, hz.STEEP_2 | hz.WET, hz.STEEP_3 | hz.HOLLOW | hz.WET, 255], np.uint8)
    assert hz.classify(f).tolist() == [1, 1, 2, 2, 3, 4, 0]


def test_auc():
    s = np.array([1, 2, 3, 4], float)
    pos = np.array([False, False, True, True])
    assert hz.auc(s, pos, ~pos) == 1.0
    assert hz.auc(np.ones(4), pos, ~pos) == 0.5


def test_road_steep_share_leaves_out_cells_with_no_valid_elevation():
    """S10: class 0 means no valid elevation. It must not dilute the steep share as if it were gentle ground."""
    assert hz.steep_share(np.array([3, 4, 1, 0, 0, 0])) == round(100 * 2 / 3, 1)
    assert hz.steep_share(np.array([1, 2, 0])) == 0.0
    assert hz.steep_share(np.array([0, 0])) is None


def test_road_segments_get_stable_ids_from_the_osm_way():
    """E6: a road stretch is named by its OSM way and its place along it; without an ID, by a hash of the source shape."""
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).resolve().parents[2] / "processing/scripts/prepare_hazards.py"
    spec = importlib.util.spec_from_file_location("prepare_hazards", path)
    ph = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ph)
    line = {"type": "LineString", "coordinates": [[85.1, 28.0], [85.2, 28.1]]}
    assert ph.segment_id({"id": "way/42"}, line, 3) == "way/42:3"
    a = ph.segment_id({}, line, 0)
    assert a.startswith("geom-") and a == ph.segment_id({"id": None}, line, 0)
    assert a != ph.segment_id({}, {"type": "LineString", "coordinates": [[85.1, 28.0], [85.3, 28.1]]}, 0)
