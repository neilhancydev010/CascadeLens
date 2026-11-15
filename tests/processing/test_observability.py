"""Radar Observability: geometry flags and per-task classes on synthetic terrain (not NASA data)."""
import h5py
import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from cascade_lens import observability as ob


def plane(dzdx_per_m, n=20, posting=40.0):
    x = np.arange(n) * posting
    return np.tile(x * dzdx_per_m, (n, 1))


LOS_WEST = (np.full((20, 20), -0.64), np.zeros((20, 20)))  # sensor to the west, as for a right-looking descending pass
INC = np.full((20, 20), 40.0)


def flags_for(dzdx):
    return ob.geometry_flags(plane(dzdx), 40.0, *LOS_WEST, INC)[2:-2, 2:-2]


def test_gentle_slope_is_visible():
    assert not flags_for(-0.2).any()  # 11 degrees toward the sensor


def test_steep_slope_toward_sensor_is_layover():
    f = flags_for(-1.0)  # 45 degrees rising toward the sensor, steeper than the 40 degree incidence
    assert (f & ob.LAYOVER).all() and not (f & ob.SHADOW).any()


def test_steep_slope_away_is_shadow():
    f = flags_for(1.5)  # 56 degrees falling away, steeper than 90 - 40 = 50
    assert (f & ob.SHADOW).all() and not (f & ob.LAYOVER).any()


def test_low_coherence_spoils_movement_but_not_disturbance():
    f = np.array([[ob.LOWCOH | ob.NOCC]], np.uint8)
    assert ob.classify(f, "movement")[0, 0] == 2
    assert ob.classify(f, "disturbance")[0, 0] == 1  # low coherence is the signal for disturbance


def test_incoherent_baseline_spoils_disturbance():
    assert ob.classify(np.array([[ob.LOWBASE]], np.uint8), "disturbance")[0, 0] == 2


def test_priority_outside_beats_everything():
    f = np.array([[ob.OUTSIDE | ob.LAYOVER | ob.LOWCOH]], np.uint8)
    assert ob.classify(f, "movement")[0, 0] == 5 and ob.classify(f, "disturbance")[0, 0] == 5


def test_summary_never_calls_missing_data_usable():
    cls = np.array([[5, 5, 5, 1]], np.uint8)
    s = ob.summary(cls, np.ones(cls.shape, bool), "movement")
    assert s["percent"]["Outside the frame checked"] == 75.0 and s["verdict"] == "Partial evidence"
    s = ob.summary(np.array([[5, 5, 5, 5, 5, 1]], np.uint8), np.ones((1, 6), bool), "movement")
    assert s["verdict"] == "Insufficient evidence"


# ---- P0.1: invalid inputs never become usable ----

def test_missing_dem_incidence_or_look_direction_is_not_assessed():
    dem = plane(-0.2)
    dem[10, 10] = np.nan
    f = ob.geometry_flags(dem, 40.0, *LOS_WEST, INC)
    assert f[10, 10] == ob.GEOM_UNKNOWN and f[10, 11] == ob.GEOM_UNKNOWN, "a missing height also spoils its neighbours' slope"
    inc = INC.copy()
    inc[5, 5] = np.nan
    inc[6, 6] = 95.0
    f = ob.geometry_flags(plane(-0.2), 40.0, *LOS_WEST, inc)
    assert f[5, 5] == ob.GEOM_UNKNOWN and f[6, 6] == ob.GEOM_UNKNOWN
    vertical = (np.zeros((20, 20)), np.zeros((20, 20)))
    assert (ob.geometry_flags(plane(-0.2), 40.0, *vertical, INC) == ob.GEOM_UNKNOWN).all(), "zero-length horizontal line of sight"
    for task in ("movement", "disturbance"):
        assert ob.classify(np.array([[ob.GEOM_UNKNOWN]]), task)[0, 0] == 6


def test_product_mask_and_missing_baseline_are_never_usable():
    for task in ("movement", "disturbance"):
        assert ob.classify(np.array([[ob.MASKED]]), task)[0, 0] == 4
        assert ob.classify(np.array([[ob.MASKED | ob.LOWCOH]]), task)[0, 0] == 4
    f = np.array([[ob.BASE_NODATA]])
    assert ob.classify(f, "disturbance")[0, 0] == 6 and ob.classify(f, "movement")[0, 0] == 1, "the baseline only matters for disturbance"


def test_disturbance_needs_a_baseline_pair():
    with pytest.raises(ValueError):
        ob.classify(np.zeros((1, 1)), "disturbance", baseline_assessed=False)
    assert ob.classify(np.zeros((1, 1)), "movement", baseline_assessed=False)[0, 0] == 1


def test_class_priority():
    f = np.array([[ob.OUTSIDE | ob.MASKED | ob.LAYOVER, ob.MASKED | ob.LAYOVER, ob.LAYOVER | ob.BASE_NODATA, ob.GEOM_UNKNOWN | ob.LOWBASE]])
    assert ob.classify(f, "disturbance").tolist() == [[5, 4, 3, 6]]


# ---- assess() on a synthetic GUNW (invented values, not NASA data) ----

FX, FY, FN, FP = 340000.0, 3130000.0, 60, 80.0
GUNW_NAME = "NISAR_L2_PR_GUNW_028_048_D_074_029_2000_SH_20260816T125812_20260816T125846_20260828T125812_20260828T125846_P05023_N_F_J_001.h5"
BASE_NAME = "NISAR_L2_PR_GUNW_026_048_D_074_028_4000_SH_20260723T125813_20260723T125848_20260816T125812_20260816T125846_P05023_N_F_J_001.h5"
TO_LL = Transformer.from_crs(32645, 4326, always_xy=True).transform


def _lonlat_poly(x0, y0, x1, y1):
    xs, ys = [x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0]
    lon, lat = TO_LL(xs, ys)
    return "POLYGON((" + ", ".join(f"{a} {b}" for a, b in zip(lon, lat)) + "))"


def _write_gunw(path, coh, cc, phase, mask, frame=74):
    with h5py.File(path, "w") as f:
        i = f.create_group("/science/LSAR/identification")
        for k, v in {"trackNumber": 48, "frameNumber": frame, "orbitPassDirection": "Descending", "lookDirection": "Left", "granuleId": path.stem,
                     "compositeReleaseId": "P05023", "productVersion": "0.0.0"}.items():
            i[k] = v
        i["boundingPolygon"] = _lonlat_poly(FX - 40, FY + 40, FX + 4000, FY - FN * FP)  # the eastern quarter is outside the frame
        u = f.create_group("/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram")
        u["xCoordinates"], u["yCoordinates"] = FX + np.arange(FN) * FP, FY - np.arange(FN) * FP
        u.create_dataset("projection", data=32645, dtype="u4")
        hh = u.create_group("HH")
        hh["coherenceMagnitude"], hh["unwrappedPhase"] = coh.astype(np.float32), phase.astype(np.float32)
        hh.create_dataset("connectedComponents", data=cc.astype(np.uint16)).attrs["_FillValue"] = 65535
        u.create_dataset("mask", data=mask.astype(np.uint8)).attrs["_FillValue"] = 255
        r = f.create_group("/science/LSAR/GUNW/metadata/radarGrid")
        r["xCoordinates"], r["yCoordinates"] = np.linspace(FX - 1000, FX + 6000, 8), np.linspace(FY + 1000, FY - 6000, 8)
        r["heightAboveEllipsoid"] = np.array([0.0, 3000.0, 6000.0])
        r["losUnitVectorX"], r["losUnitVectorY"] = np.full((3, 8, 8), -0.55), np.full((3, 8, 8), 0.17)
        r["incidenceAngle"] = np.full((3, 8, 8), 35.0)


def _write_dem(path, hole):
    t = from_origin(FX - 500, FY + 500, 30, 30)
    z = np.full((200, 200), 1500.0, np.float32)
    (x0, y0, x1, y1) = hole
    c0, c1 = int((x0 - (FX - 500)) / 30), int((x1 - (FX - 500)) / 30)
    r0, r1 = int(((FY + 500) - y0) / 30), int(((FY + 500) - y1) / 30)
    z[r0:r1, c0:c1] = np.nan
    with rasterio.open(path, "w", driver="GTiff", width=200, height=200, count=1, dtype="float32", crs="EPSG:32645", transform=t, nodata=np.nan) as d:
        d.write(z, 1)


def _cell(r, R, row, col):
    """Analysis cell holding the centre of product pixel (row, col), nudged 10 m into the cell."""
    x, y = FX + col * FP + 10, FY - row * FP - 10
    inv = ~R["transform"]
    c, rr = inv * (x, y)
    return int(rr), int(c)


@pytest.fixture
def synthetic_case(tmp_path):
    coh, cc, phase, mask = np.full((FN, FN), 0.7), np.ones((FN, FN)), np.full((FN, FN), 2.5), np.full((FN, FN), 11)
    coh[10:20, 10:20], mask[10:20, 10:20], phase[10:20, 10:20] = 0.12, 10, 0.0  # a source zone: values present, mask says invalid subswath
    coh[30:35, 30:35] = 0.1  # low coherence, otherwise valid
    cc[40:45, 40:45] = 65535  # component fill with finite phase
    phase[45:50, 10:15] = 0.0  # zero-fill inside component 1
    _write_gunw(tmp_path / GUNW_NAME, coh, cc, phase, mask)
    bcoh = np.full((FN, FN), 0.8)
    bcoh[50:55, 20:25] = np.nan  # baseline holds nothing here
    _write_gunw(tmp_path / BASE_NAME, bcoh, np.ones((FN, FN)), np.full((FN, FN), 1.0), np.full((FN, FN), 11))
    _write_dem(tmp_path / "dem.tif", (FX + 30 * FP - 40, FY - 20 * FP + 40, FX + 35 * FP - 40, FY - 25 * FP + 40))
    lon, lat = TO_LL([FX + 100, FX + 4600], [FY - 4600, FY - 100])
    bounds = [min(lon), min(lat), max(lon), max(lat)]
    return tmp_path, bounds


def test_assess_never_calls_masked_or_missing_inputs_usable(synthetic_case):
    d, bounds = synthetic_case
    R = ob.assess(d / GUNW_NAME, d / BASE_NAME, d / "dem.tif", bounds)
    f = R["flags"]
    dist, move = ob.classify(f, "disturbance"), ob.classify(f, "movement")
    src = _cell(ob, R, 15, 15)
    assert f[src] & ob.MASKED, "the product's own mask must reach the flags"
    assert dist[src] == 4 and move[src] == 4, "values present but flagged invalid by the product: never usable"
    low = _cell(ob, R, 32, 32)
    assert move[low] == 2 and dist[low] == 1, "low coherence spoils movement, not disturbance"
    assert move[_cell(ob, R, 42, 42)] == 2, "component fill is not a component"
    assert move[_cell(ob, R, 47, 12)] == 2, "zero-filled phase is not unwrapped phase"
    hole = _cell(ob, R, 22, 32)
    assert f[hole] & ob.GEOM_UNKNOWN and dist[hole] == 6 and move[hole] == 6, "no DEM: not assessed"
    nobase = _cell(ob, R, 52, 22)
    assert dist[nobase] == 6 and move[nobase] == 1
    assert move[_cell(ob, R, 5, 55)] == 5 and dist[_cell(ob, R, 5, 55)] == 5, "east of the footprint"
    assert move[_cell(ob, R, 5, 5)] == 1 and dist[_cell(ob, R, 5, 5)] == 1
    assert R["methodVersion"] == ob.METHOD_VERSION and R["ccFillValue"] == 65535
    assert not (f == ob.FLAG_NODATA).any()


def test_sensitivity_uses_the_movement_rule(synthetic_case):
    d, bounds = synthetic_case
    R = ob.assess(d / GUNW_NAME, d / BASE_NAME, d / "dem.tif", bounds)
    inside = (R["flags"] & ob.OUTSIDE) == 0
    expected = round(100 * float((ob.classify(R["flags"], "movement")[inside] == 1).mean()), 1)
    assert R["sensitivity"]["movementUsablePct"]["0.3"] == expected, "at the project threshold it equals the class map"
    s = R["sensitivity"]["movementUsablePct"]
    assert s["0.2"] >= s["0.3"] >= s["0.4"]


def test_baseline_from_another_frame_is_refused(synthetic_case, tmp_path):
    d, bounds = synthetic_case
    other = tmp_path / ("x" + BASE_NAME)
    _write_gunw(other, np.full((FN, FN), 0.8), np.ones((FN, FN)), np.ones((FN, FN)), np.full((FN, FN), 11), frame=75)
    with pytest.raises(ValueError, match="not comparable"):
        ob.assess(d / GUNW_NAME, other, d / "dem.tif", bounds)


def test_a_product_without_its_mask_is_refused(synthetic_case):
    d, bounds = synthetic_case
    with h5py.File(d / GUNW_NAME, "a") as f:
        del f["/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/mask"]
    with pytest.raises(ValueError, match="mask"):
        ob.assess(d / GUNW_NAME, None, d / "dem.tif", bounds)


def test_a_neighbouring_frame_fills_only_cells_the_first_frame_does_not_cover():
    O, NODATA = ob.OUTSIDE, ob.FLAG_NODATA
    first = np.array([0, ob.LOWCOH, O, O, O, NODATA])
    other = np.array([ob.MASKED, 0, ob.LAYOVER, O, NODATA, 0])
    combined, took = ob.combine_frames(first, other)
    assert combined.tolist() == [0, ob.LOWCOH, ob.LAYOVER, O, O, NODATA]  # the first frame wins where both cover a cell
    assert took.tolist() == [False, False, True, False, False, False]
    with pytest.raises(ValueError):
        ob.combine_frames(first, other[:3])
