"""Verification harness (verify.py): skill scores worked out by hand, splits and the leakage guard."""
from datetime import date, datetime, timezone

import numpy as np
import pytest

from cascade_lens import verify as v


def test_scores_match_the_textbook_definitions():
    c = v.Contingency(hits=8, misses=2, false_alarms=4, correct_negatives=86)
    assert c.pod == 0.8 and c.far == pytest.approx(1 / 3) and c.csi == pytest.approx(8 / 14) and c.bias == 1.2
    assert v.Contingency(0, 0, 0).pod is None and v.Contingency(0, 0, 0).csi is None


def test_daily_contingency():
    p = np.array([1, 1, 0, 0, 1, 0], bool)
    o = np.array([1, 0, 1, 0, 1, 0], bool)
    c = v.contingency(p, o)
    assert (c.hits, c.misses, c.false_alarms, c.correct_negatives) == (2, 1, 1, 2)
    with pytest.raises(ValueError):
        v.contingency(p, o[:3])


def test_event_matching_counts_a_warning_once_and_never_after_the_event():
    events = [date(2024, 7, 10), date(2024, 7, 11), date(2024, 8, 1)]
    warnings = [date(2024, 7, 10), date(2024, 7, 20), date(2024, 8, 2)]
    c = v.match_events(warnings, events, window_days=1)
    # 10 Jul warning hits the 10 Jul event; 11 Jul has no unused warning in its window; 2 Aug is after 1 Aug: a miss, and a false alarm
    assert (c.hits, c.misses, c.false_alarms) == (1, 2, 2)


def test_chronological_split_never_tests_on_the_past():
    t = [date(2019, 1, 1), date(2021, 6, 1), date(2022, 1, 1), date(2025, 7, 1), date(2024, 12, 31)]
    tr, va, te = v.chronological_split(t, date(2021, 12, 31), date(2024, 12, 31))
    assert tr == [0, 1] and va == [2, 4] and te == [3]
    assert max(t[i] for i in tr) < min(t[i] for i in te)


def test_the_leakage_guard_refuses_unpublished_and_undated_records():
    recs = [{"id": 1, "available_at": "2024-07-01T04:00:00Z"}, {"id": 2, "available_at": "2024-07-01T18:00:00Z"}, {"id": 3}]
    out = v.available_by(recs, datetime(2024, 7, 1, 12, tzinfo=timezone.utc))
    assert [r["id"] for r in out] == [1]


def test_spatial_blocks_keep_neighbours_together_and_are_reproducible():
    x = np.array([10, 20, 990, 1010, 2500, 2600], float)
    y = np.zeros(6)
    f = v.spatial_blocks(x, y, block_m=1000, folds=3, seed=4)
    assert f[0] == f[1] == f[2] and f[3] != f[0] and f[4] == f[5]
    assert (v.spatial_blocks(x, y, 1000, 3, seed=4) == f).all()


def test_auc_by_ranks():
    assert v.auc(np.array([0.1, 0.4, 0.35, 0.8]), np.array([0, 0, 1, 1], bool)) == 0.75
    assert v.auc(np.array([1, 1, 1, 1.0]), np.array([0, 1, 0, 1], bool)) == 0.5
    assert v.auc(np.array([1.0, 2.0]), np.array([1, 1], bool)) is None


def test_nse():
    o = np.array([1.0, 2.0, 3.0])
    assert v.nse(o, o) == 1.0 and v.nse(np.full(3, 2.0), o) == 0.0


def test_windowed_scoring_counts_leads_and_ignores_the_edges():
    w = np.zeros((10, 2), bool)
    o = np.zeros((10, 2), bool)
    w[2, 0] = True; o[4, 0] = True   # lead 2: a hit
    w[5, 1] = True                   # nothing follows at place 1: a false alarm
    o[9, 1] = True                   # no warning 2 to 3 days before (day 5 is 4 days back): a miss
    o[1, 0] = True                   # too early to have had a warning: left out
    c = v.windowed(w, o, lead_min=2, lead_max=3)
    assert (c.hits, c.misses, c.false_alarms) == (1, 1, 1)
    same_day = v.windowed(w, o, lead_min=0, lead_max=1)
    assert same_day.hits == 0 and same_day.false_alarms == 2


def test_shuffled_warnings_keep_each_places_count_per_block_and_are_reproducible():
    rng = np.random.default_rng(0)
    o = rng.random((60, 3)) < 0.1
    w = np.roll(o, -2, axis=0)  # perfect warnings, two days ahead
    blocks = np.repeat(np.arange(2), 30)
    real = v.windowed(w, o, 2, 2).csi
    chance = v.shuffled_csi(w, o, blocks, 2, 2, n=200, seed=1)
    assert real == 1.0 and np.nanmax(chance) < real
    assert np.array_equal(chance, v.shuffled_csi(w, o, blocks, 2, 2, n=200, seed=1), equal_nan=True)
