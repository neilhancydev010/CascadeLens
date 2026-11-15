"""Dam-break scenario arithmetic (scenario.py) on synthetic terrain. Invented values, not NASA data.

These check the published formulas as written, the depression-filled drainage, and the Manning solve. They do not
make the scenario a prediction: it stays a labelled what-if with assumed breach depths."""
import math

import numpy as np

from cascade_lens import scenario


def test_peak_flow_formulas_match_their_published_form():
    v, h = 30e6, 20.0
    assert math.isclose(scenario.FORMULAS["popov"][1](v, h), 0.0048 * v ** 0.896)
    assert math.isclose(scenario.FORMULAS["huggel"][1](v, h), 0.00077 * v ** 1.017)
    assert math.isclose(scenario.FORMULAS["costa"][1](v, h), 0.0158 * (h * v * 9800.0) ** 0.41)


def test_peak_flow_grows_with_volume_and_huggel_is_the_upper_envelope():
    for f in ("popov", "huggel", "costa"):
        q = [scenario.FORMULAS[f][1](v, 20.0) for v in (1e6, 1e7, 1e8)]
        assert q[0] < q[1] < q[2]
    v = 30e6
    assert scenario.FORMULAS["huggel"][1](v, 20.0) > scenario.FORMULAS["popov"][1](v, 20.0)


def _follow(parent, start, cols):
    seen, i = set(), start
    while parent[i] != -1:
        assert i not in seen, "drainage must never loop"
        seen.add(i)
        j = parent[i]
        (r, c), (rr, cc) = divmod(i, cols), divmod(j, cols)
        assert max(abs(r - rr), abs(c - cc)) == 1, "water moves to a neighbour"
        i = j
    return divmod(i, cols)


def test_drainage_reaches_the_edge_from_every_cell_even_through_a_pit():
    R = C = 25
    yy, xx = np.mgrid[:R, :C]
    z = 100.0 + 2.0 * xx  # rises to the east, drains west
    z[12, 12] = 50.0  # a closed pit in the middle
    parent = scenario.drainage(z)
    for start in (12 * C + 12, 5 * C + 20, 20 * C + 3):
        r, c = _follow(parent, start, C)
        assert r in (0, R - 1) or c in (0, C - 1)


def test_drainage_out_of_a_pit_leaves_on_the_low_side():
    R = C = 25
    yy, xx = np.mgrid[:R, :C]
    z = 100.0 + 2.0 * xx
    z[12, 12] = 50.0
    r, c = _follow(scenario.drainage(z), 12 * C + 12, C)
    assert c == 0


def test_manning_solve_carries_the_requested_flow_in_a_rectangular_channel():
    s = np.arange(-scenario.HALF_WIDTH_M, scenario.HALF_WIDTH_M + 1, 30.0)
    width_m = 120.0
    prof = np.where(np.abs(s) <= width_m / 2, 1000.0, 1100.0)  # flat bed, 100 m walls
    sec = {"s": s, "prof": prof, "slope": 0.02}
    q, n = 2000.0, 0.1
    h, v, (a, b) = scenario._hydraulics(sec, q, n)
    wet = b - a + 1
    area, top = h * wet * 30.0, wet * 30.0
    q_back = area * (area / (top + 2 * h)) ** (2 / 3) * 0.02 ** 0.5 / n
    assert abs(q_back - q) / q < 1e-3
    assert math.isclose(v, q_back / area, rel_tol=1e-3)


def test_rougher_channel_is_deeper_and_slower():
    s = np.arange(-scenario.HALF_WIDTH_M, scenario.HALF_WIDTH_M + 1, 30.0)
    prof = 1000.0 + 0.05 * np.abs(s)  # a V-shaped valley
    sec = {"s": s, "prof": prof, "slope": 0.03}
    h1, v1, _ = scenario._hydraulics(sec, 5000.0, scenario.N_RANGE[0])
    h2, v2, _ = scenario._hydraulics(sec, 5000.0, scenario.N_RANGE[1])
    assert h2 > h1 and v2 < v1


# ---- The shipped scenario can be rebuilt by hand from its sections table ----
import csv  # noqa: E402
import json  # noqa: E402
import pathlib  # noqa: E402

import pytest  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
CSV = ROOT / "data/qa/tsho-rolpa-2026-scenario-sections.csv"
MANIFEST = ROOT / "frontend/public/data/manifests/tsho-rolpa-2026.json"


def _shipped():
    if not CSV.exists():
        pytest.skip("sections table not built")
    sc = json.loads(MANIFEST.read_text(encoding="utf-8"))["lake"]["scenario"]
    with CSV.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return sc, rows


def test_sections_table_cumulative_times_equal_the_manifest_arrival_times():
    sc, rows = _shipped()
    assert list(rows[0].keys()) == scenario.SECTION_COLUMNS
    for case in sc["scenarios"]:
        mine = [r for r in rows if float(r["breach_m"]) == case["breachM"]]
        assert len(mine) == len(case["arrival"]) == case["floors"]["sections"]
        for r, (km, fast, slow) in zip(mine, case["arrival"]):
            assert round(float(r["km"]), 1) == km
            # From the seconds column: the minutes column is itself rounded, and 27.5 could round either way
            assert round(float(r["fast_cum_s"]) / 60) == fast
            assert round(float(r["slow_cum_s"]) / 60) == slow
        # Each segment time is its length over the floored speed, and they add up
        cum = 0.0
        for r in mine:
            speed = max(float(r["slow_v_ms"]), scenario.SPEED_FLOOR)
            assert math.isclose(float(r["slow_seg_s"]), float(r["slow_seg_m"]) / speed, rel_tol=1e-3, abs_tol=0.02)
            cum += float(r["slow_seg_s"])
        assert math.isclose(cum, float(mine[-1]["slow_cum_s"]), rel_tol=1e-4)
        # The counted floors match the flags in the table
        assert case["floors"]["slope"] == sum(int(r["slope_floor_applied"]) for r in mine)
        assert case["floors"]["speedFast"] == sum(int(r["fast_speed_floor_applied"]) for r in mine)
        assert case["floors"]["speedSlow"] == sum(int(r["slow_speed_floor_applied"]) for r in mine)


def test_lake_area_range_orders_the_peaks_low_mean_high():
    sc, _ = _shipped()
    lo, mean, hi = sc["areaRangeKm2"]
    assert lo <= mean <= hi
    for case in sc["scenarios"]:
        p = case["peaksByArea"]
        for f in ("popov", "costa", "huggel"):
            assert p["low"][f] <= p["mean"][f] <= p["high"][f]
        assert case["peakM3s"] == p["mean"]
        assert case["peakRange"] == [min(p["low"]["popov"], p["low"]["costa"]), max(p["high"]["popov"], p["high"]["costa"])]
        assert case["volumeRangeM3"][0] <= case["volumeM3"] <= case["volumeRangeM3"][1]


def test_kinematic_sensitivity_is_forty_percent_shorter_and_only_a_side_line():
    sc, _ = _shipped()
    for case in sc["scenarios"]:
        last, kin = case["arrival"][-1], case["arrivalKinematic"][-1]
        assert abs(kin[1] - last[1] * 0.6) <= 1 and abs(kin[2] - last[2] * 0.6) <= 1


def test_shipped_peaks_recompute_from_the_formulas():
    sc, _ = _shipped()
    lo, mean, hi = sc["areaRangeKm2"]
    for case in sc["scenarios"]:
        for name, a in (("low", lo), ("mean", mean), ("high", hi)):
            v, peaks = scenario.volume_and_peaks(a, case["breachM"])
            assert {k: round(q) for k, q in peaks.items()} == case["peaksByArea"][name]


def test_travel_applies_the_speed_floor_and_flags_it():
    s = np.arange(-scenario.HALF_WIDTH_M, scenario.HALF_WIDTH_M + 1, 30.0)
    prof = np.where(np.abs(s) <= 60, 1000.0, 1100.0)
    secs = [{"km": 0.5 * (i + 1), "s": s, "prof": prof, "slope": scenario.SLOPE_FLOOR} for i in range(3)]
    rows = scenario.travel(secs, 0.5, 0.15)  # a trickle in a rough channel: slower than the floor
    assert all(r["speedFloor"] for r in rows)
    assert math.isclose(rows[-1]["cumS"], 1500 / scenario.SPEED_FLOOR)
