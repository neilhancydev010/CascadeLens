"""Coherence control series on synthetic GUNW pairs (invented values, not NASA data)."""
import h5py
import numpy as np
import pytest
from pyproj import Transformer
from shapely.geometry import Polygon

from cascade_lens import coherence_series as cs

X0, Y0, N, P = 340000.0, 3130000.0, 100, 80.0
TO_LL = Transformer.from_crs(32645, 4326, always_xy=True).transform
BEFORE = "NISAR_L2_PR_GUNW_026_048_D_074_028_4000_SH_20260723T125813_20260723T125848_20260816T125812_20260816T125846_P05023_N_F_J_001.h5"
ACROSS = "NISAR_L2_PR_GUNW_028_048_D_074_029_2000_SH_20260816T125812_20260816T125846_20260828T125812_20260828T125846_P05023_N_F_J_001.h5"


def zone_lonlat():
    xs = [X0 + 40 * P, X0 + 60 * P, X0 + 60 * P, X0 + 40 * P]
    ys = [Y0 - 40 * P, Y0 - 40 * P, Y0 - 60 * P, Y0 - 60 * P]
    lon, lat = TO_LL(xs, ys)
    return Polygon(list(zip(lon, lat)))


def make(path, inside, outside=0.6, frame=74, bandwidth=None, masked_low=False):
    coh = np.full((N, N), outside, np.float32)
    coh[40:60, 40:60] = inside
    mask = np.full((N, N), 11, np.uint8)
    if masked_low:
        coh[40:45, 40:60] = 0.01  # values present but the product flags them: must not pull the median down
        mask[40:45, 40:60] = 10
    rng = np.random.default_rng(3)
    coh += rng.normal(0, 0.02, coh.shape).astype(np.float32)
    with h5py.File(path, "w") as f:
        i = f.create_group("/science/LSAR/identification")
        i["trackNumber"], i["frameNumber"], i["orbitPassDirection"] = 48, frame, "Descending"
        root = f.create_group("/science/LSAR/GUNW/grids/frequencyA")
        if bandwidth:
            root["rangeBandwidth"] = bandwidth
        u = root.create_group("unwrappedInterferogram")
        u["xCoordinates"], u["yCoordinates"] = X0 + np.arange(N) * P, Y0 - np.arange(N) * P
        u.create_dataset("projection", data=32645, dtype="u4")
        u["HH/coherenceMagnitude"] = coh
        u["mask"] = mask


def test_series_reports_medians_mode_interval_and_block_intervals(tmp_path):
    make(tmp_path / BEFORE, inside=0.45, bandwidth=40e6)
    make(tmp_path / ACROSS, inside=0.25, masked_low=True, bandwidth=20e6)
    s = cs.series([tmp_path / ACROSS, tmp_path / BEFORE], zone_lonlat(), "Test zone", "2026-08-26", n_boot=200)
    before, across = s["pairs"]
    assert before["pair"] == ["2026-07-23", "2026-08-16"] and before["days"] == 24 and across["days"] == 12, "sorted by date"
    assert (before["mode"], across["mode"]) == ("4000", "2000") and (before["rangeBandwidthHz"], across["rangeBandwidthHz"]) == (40e6, 20e6)
    assert before["inside"] == pytest.approx(0.45, abs=0.01) and across["inside"] == pytest.approx(0.25, abs=0.01), "masked pixels are excluded"
    assert across["outside"] == pytest.approx(0.6, abs=0.01)
    assert 70 < across["insideValidPct"] < 85, "about a quarter of the zone is product-masked (edge pixels vary with rasterisation)"
    lo, hi = across["insideCi95"]
    assert lo <= across["inside"] <= hi
    assert "block bootstrap" in s["ciMethod"] and s["methodVersion"] == cs.METHOD_VERSION


def test_series_is_deterministic(tmp_path):
    make(tmp_path / ACROSS, inside=0.25)
    a = cs.pair_stats(tmp_path / ACROSS, zone_lonlat(), n_boot=100)
    b = cs.pair_stats(tmp_path / ACROSS, zone_lonlat(), n_boot=100)
    assert a == b


def test_block_intervals_are_wider_than_pretending_pixels_are_independent():
    rng = np.random.default_rng(0)
    rows, cols = np.mgrid[0:60, 0:60]
    field = np.repeat(np.repeat(rng.normal(0.3, 0.1, (6, 6)), 10, 0), 10, 1)  # strongly correlated within 10 x 10 blocks
    v = field.ravel()
    block = cs.block_bootstrap_ci(v, rows.ravel(), cols.ravel(), 10, 300, np.random.default_rng(1))
    naive = cs.block_bootstrap_ci(v, rows.ravel(), cols.ravel(), 1, 300, np.random.default_rng(1))
    assert block[1] - block[0] > 3 * (naive[1] - naive[0])


def test_pairs_from_different_frames_are_refused(tmp_path):
    make(tmp_path / BEFORE, inside=0.45, frame=75)
    make(tmp_path / ACROSS, inside=0.25)
    with pytest.raises(ValueError, match="different tracks or frames"):
        cs.series([tmp_path / BEFORE, tmp_path / ACROSS], zone_lonlat(), "z", "2026-08-26", n_boot=50)


def test_a_product_without_its_mask_is_refused(tmp_path):
    make(tmp_path / ACROSS, inside=0.25)
    with h5py.File(tmp_path / ACROSS, "a") as f:
        del f["/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/mask"]
    with pytest.raises(ValueError, match="mask"):
        cs.pair_stats(tmp_path / ACROSS, zone_lonlat(), n_boot=10)
