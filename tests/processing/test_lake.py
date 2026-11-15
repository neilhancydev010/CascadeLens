"""Lake area method (lake.py) on synthetic backscatter. Invented values, not NASA data.

These test the computation behind the Tsho Rolpa lake series: the dark-water detection, its threshold range,
the compare window and the downhill route. They do not validate any real lake area."""
import numpy as np
from scipy import ndimage

from cascade_lens import lake

N = 120


def scene(radius=30, water=0.002, land=0.5, centre=(60, 60)):
    """Bright rough ground (about -2 dB in HH + HV, linear power) with one calm, dark lake disk (about -26 dB)."""
    yy, xx = np.mgrid[:N, :N]
    disk = (yy - centre[0]) ** 2 + (xx - centre[1]) ** 2 <= radius ** 2
    hh = np.where(disk, water, land)
    hv = np.where(disk, water / 4, land / 4)
    return hh, hv, disk


def seed_at(r, c, size=3):
    s = np.zeros((N, N), bool)
    s[r - size:r + size, c - size:c + size] = True
    return s


def test_finds_the_dark_disk_that_touches_the_seed():
    hh, hv, disk = scene()
    found = lake.detect_lake(hh, hv, seed_at(60, 60), lake.THRESHOLD_DB)
    within_one_pixel(found, disk)


def within_one_pixel(found, disk):
    """The 3x3 smoothing can move the shoreline by up to one pixel, inward or outward depending on contrast."""
    assert found[ndimage.binary_erosion(disk)].all()
    assert not found[~ndimage.binary_dilation(disk)].any()


def test_finds_nothing_when_the_seed_misses_the_water():
    hh, hv, _ = scene()
    assert not lake.detect_lake(hh, hv, seed_at(10, 10), lake.THRESHOLD_DB).any()


def test_keeps_only_the_dark_area_under_the_seed():
    hh, hv, disk = scene(radius=20, centre=(40, 40))
    other = scene(radius=15, centre=(95, 95))[2]
    hh, hv = np.where(other, 0.002, hh), np.where(other, 0.0005, hv)
    found = lake.detect_lake(hh, hv, seed_at(40, 40), lake.THRESHOLD_DB)
    within_one_pixel(found, disk)
    assert not found[other].any()


def test_a_thin_dark_strip_is_not_water():
    """Radar shadow edges are thin and dark; opening removes them so they cannot join the lake."""
    hh, hv, disk = scene()
    hh, hv = hh.copy(), hv.copy()
    hh[:, 100:102], hv[:, 100:102] = 0.002, 0.0005
    found = lake.detect_lake(hh, hv, seed_at(60, 60), lake.THRESHOLD_DB)
    assert not found[:, 100:102].any()


def test_bright_spots_inside_the_lake_are_filled():
    hh, hv, disk = scene()
    hh, hv = hh.copy(), hv.copy()
    hh[58:61, 58:61], hv[58:61, 58:61] = 0.2, 0.05  # a floating block or a bright pixel
    found = lake.detect_lake(hh, hv, seed_at(50, 50), lake.THRESHOLD_DB)
    assert found[58:61, 58:61].all()


def test_the_threshold_range_brackets_the_central_estimate():
    """The method range reruns at 1 dB brighter and darker. A darker threshold can only shrink the dark area."""
    yy, xx = np.mgrid[:N, :N]
    r = np.hypot(yy - 60, xx - 60)
    total_db = np.clip(-14 + 0.25 * r, -14, -2)  # backscatter rising smoothly from the lake centre outwards
    p = 10 ** (total_db / 10) / 2
    seed = seed_at(60, 60)
    areas = {t: int(lake.detect_lake(p, p, seed, t).sum()) for t in (lake.THRESHOLD_RANGE[1], lake.THRESHOLD_DB, lake.THRESHOLD_RANGE[0])}
    lo, mid, hi = areas[-8.0], areas[-7.0], areas[-6.0]
    assert lake.THRESHOLD_RANGE == (-6.0, -8.0)
    assert 0 < lo < mid < hi


def test_compare_window_holds_the_lake_at_four_by_three_inside_the_clip():
    _, _, disk = scene(radius=20, centre=(30, 90))
    r0, r1, c0, c1 = lake.compare_window(disk, N, N, pad=5)
    assert 0 <= r0 < r1 <= N and 0 <= c0 < c1 <= N
    rr, cc = np.where(disk)
    assert r0 <= rr.min() and rr.max() < r1 and c0 <= cc.min() and cc.max() < c1
    assert abs((c1 - c0) / (r1 - r0) - 4 / 3) < 0.05


def test_compare_window_falls_back_to_the_whole_clip_without_a_lake():
    assert lake.compare_window(np.zeros((N, N), bool), N, N, pad=5) == (0, N, 0, N)


def test_flow_path_starts_at_the_lowest_shore_and_runs_downhill():
    _, _, disk = scene(radius=10, centre=(60, 60))
    yy, xx = np.mgrid[:N, :N]
    z = 5000.0 - 10.0 * xx - 0.5 * yy  # slopes down to the east
    out = lake.flow_path(z, disk)
    path = out["flowPath"]
    heights = [p[2] for p in path]
    assert path[0][:2] == out["outlet"]
    assert all(b <= a + 1e-6 for a, b in zip(heights, heights[1:]))
    assert path[-1][0] == N - 1  # leaves the block on the low (east) side


def test_flow_path_is_empty_without_a_lake():
    assert lake.flow_path(np.zeros((N, N)), np.zeros((N, N), bool)) == {}
