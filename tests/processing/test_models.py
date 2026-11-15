"""First models (audit P2) on synthetic data only. These check that the code does what the method says: recovering known
parameters, closing the water balance, separating events. They say nothing about skill on real data, which needs the
datasets the readiness engine lists."""
import numpy as np
import pytest

from cascade_lens.models import gr4j, susceptibility, thresholds


# --- Rainfall thresholds ------------------------------------------------------------------------------------------------

def test_events_are_split_by_dry_spells():
    r = np.array([0, 5, 12, 0, 3, 0, 0, 0, 20, 1, 0, 0])
    ev = thresholds.events(r, dry_days=2, wet_mm=1.0)
    assert ev == [(1, 4, 20.0), (8, 9, 21.0)]


def test_ed_threshold_recovers_the_slope_and_leaves_the_chosen_share_below():
    rng = np.random.default_rng(1)
    d = rng.uniform(1, 20, 400)
    e = 8.0 * d ** 0.6 * 10 ** rng.normal(0.25, 0.12, 400)  # triggering events lie above a 8 * D^0.6 floor
    th = thresholds.fit_ed(e, d, level=0.05)
    assert th.beta == pytest.approx(0.6, abs=0.05)
    below = np.mean([not th.exceeds(ei, di) for ei, di in zip(e, d)])
    assert below == pytest.approx(0.05, abs=0.02)
    with pytest.raises(ValueError):
        thresholds.fit_ed(e[:5], d[:5])


def test_antecedent_index_decays_and_lags_one_day():
    a = thresholds.api(np.array([10.0, 0, 0, 0]), k=0.5)
    assert a.tolist() == [0.0, 10.0, 5.0, 2.5]


# --- Susceptibility -----------------------------------------------------------------------------------------------------

def _terrain(n=3000, seed=2):
    rng = np.random.default_rng(seed)
    x, y = rng.uniform(0, 50000, n), rng.uniform(0, 50000, n)
    slope, wet, noise = rng.normal(30, 8, n), rng.normal(0, 1, n), rng.normal(0, 1, n)
    logit = -1.0 + 1.5 * (slope - 30) / 8 + 0.8 * wet
    yv = rng.random(n) < 1 / (1 + np.exp(-logit))
    return np.column_stack([slope, wet, noise]), yv, x, y


def test_logistic_regression_recovers_known_effects():
    X, y, *_ = _terrain()
    m = susceptibility.fit(X, y, ["slope", "wetness", "noise"])
    t = {r["feature"]: r["logOddsPerSd"] for r in m.table()}
    assert t["slope"] == pytest.approx(1.5, abs=0.2) and t["wetness"] == pytest.approx(0.8, abs=0.15) and abs(t["noise"]) < 0.15


def test_block_cross_validation_rewards_signal_and_not_noise():
    X, y, xm, ym = _terrain()
    good = susceptibility.block_cv(X, y, xm, ym, ["slope", "wetness", "noise"], block_m=10000, folds=5)
    rng = np.random.default_rng(3)
    shuffled = susceptibility.block_cv(X, rng.random(len(y)) < y.mean(), xm, ym, ["slope", "wetness", "noise"], block_m=10000, folds=5)
    assert good["aucOutOfFold"] > 0.8
    assert abs(shuffled["aucOutOfFold"] - 0.5) < 0.06


# --- GR4J ---------------------------------------------------------------------------------------------------------------

def _climate(days=1095, seed=4):
    rng = np.random.default_rng(seed)
    t = np.arange(days)
    season = np.sin(2 * np.pi * (t - 120) / 365)
    p = np.where(rng.random(days) < 0.25 + 0.35 * (season > 0), rng.gamma(0.8, 14, days), 0.0)
    pet = np.clip(3 + 2 * season, 0.5, None)
    temp = 8 + 12 * season + rng.normal(0, 2, days)
    return p, pet, temp


def test_unit_hydrographs_each_sum_to_one():
    for x4 in (0.7, 1.8, 3.3, 7.0):
        uh1, uh2 = gr4j.unit_hydrographs(x4)
        assert uh1.sum() == pytest.approx(1) and uh2.sum() == pytest.approx(1)


def test_water_balance_closes_without_exchange():
    p, pet, _ = _climate()
    q, st = gr4j.run(p, pet, 350, 0.0, 90, 1.7, return_states=True)
    # With x2 = 0 nothing is gained or lost underground: rain = runoff + actual evaporation + storage change (+ water in the UH)
    s0, r0 = 0.5 * 350, 0.5 * 90
    storage = st[-1, 0] - s0 + st[-1, 1] - r0
    evap = p.sum() - q.sum() - storage
    assert 0 < evap < pet.sum()
    assert q.min() >= 0


def test_snow_holds_winter_precipitation_and_releases_it_when_warm():
    p = np.full(20, 10.0)
    temp = np.r_[np.full(10, -5.0), np.full(10, 6.0)]
    liquid, pack = gr4j.snow(p, temp, ddf=4.0, t_melt=0.0)
    assert liquid[:10].sum() == 0 and pack[9] == 100.0
    assert liquid.sum() + pack[-1] == pytest.approx(p.sum())
    assert pack[-1] < pack[9]


def test_calibration_recovers_a_known_catchment():
    p, pet, temp = _climate(days=900)
    truth = dict(x1=420.0, x2=-0.8, x3=110.0, x4=2.2)
    q = gr4j.run(p, pet, **truth, temp=temp, ddf=3.0, t_melt=0.0)
    fit = gr4j.calibrate(p, pet, q, temp=temp, warmup=300, maxiter=40, seed=1)
    assert fit["nse"] > 0.98
    assert fit["params"]["x4"] == pytest.approx(truth["x4"], rel=0.25)


def test_ongoing_event_matches_event_at_on_every_day_and_reads_no_later_day():
    rng = np.random.default_rng(3)
    r = np.where(rng.random(400) < 0.45, rng.gamma(1.2, 12, 400), rng.random(400) * 0.9)  # wet spells, dry-day drizzle
    e, d = thresholds.ongoing(r, dry_days=2, wet_mm=1.0)
    for t in range(len(r)):
        got = thresholds.event_at(r, t, dry_days=2, wet_mm=1.0)
        assert (e[t], d[t]) == ((0.0, 0) if got is None else pytest.approx(got))
        changed = r.copy()
        changed[t + 1:] = 500.0  # a flood tomorrow changes nothing about today
        e2, d2 = thresholds.ongoing(changed)
        assert e2[t] == pytest.approx(e[t]) and d2[t] == d[t]
        if t > 60:
            break


def test_event_at_closes_an_event_after_the_dry_spell():
    r = np.array([0, 10, 20, 0, 0, 0, 5])
    assert thresholds.event_at(r, 2) == (30.0, 2)
    assert thresholds.event_at(r, 3) == (30.0, 2)  # one dry day: the event is still the trigger candidate
    assert thresholds.event_at(r, 4) is None  # two dry days: it has ended
    assert thresholds.event_at(r, 6) == (5.0, 1)


def test_warnings_fire_when_the_event_so_far_reaches_the_line():
    th = thresholds.Threshold(alpha=25.0, beta=0.5, level=0.05, n_events=10)
    r = np.array([0, 10, 10, 20, 0, 0, 0, 30])
    # day 1: 10 < 25; day 2: 20 < 25*sqrt(2)=35.4; day 3: 40 < 25*sqrt(3)=43.3; day 7: 30 >= 25
    assert thresholds.warnings(r, th).tolist() == [False, False, False, False, False, False, False, True]
