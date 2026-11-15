"""Readiness engine (readiness.py) on a synthetic catalogue: every rung of the ladder, and every dataset condition."""
from datetime import datetime, timezone

import pytest

from cascade_lens import readiness as rd

NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)
CAT = {
    "areas": {"R": [84.0, 27.0, 86.0, 29.0]},
    "windows": {"W": ["2020-01-01", "2024-12-31"]},
    "datasets": {"RAIN": {"name": "Rainfall"}, "GAUGE": {"name": "Gauges"}, "SOIL": {"name": "Soil"}},
    "capabilities": [],
}
RAIN = {"dataset": "RAIN", "area": "R", "window": "W", "variables": ["precipitation"], "units": {"precipitation": "mm/h"}, "maxResolutionM": 11200}
CAP = {"id": "flood.X", "family": "flood", "name": "X", "needs": [RAIN, {"dataset": "GAUGE", "area": "R"}, {"dataset": "SOIL", "essential": False}]}


def src(dataset, **kw):
    base = {"dataset": dataset, "_path": f"data/raw/{dataset}/SOURCE.json", "licence": "CC BY 4.0", "crs": "EPSG:4326",
            "spatial_extent": [84.5, 27.5, 85.5, 28.5], "time_extent": ["2016-01-01", "2026-10-31"], "variables": ["precipitation"],
            "units": {"precipitation": "mm/h"}, "resolution_m": 11000, "available_at": "2026-11-12T00:00:00Z"}
    return {**base, **kw}


def ok_sources():
    return {"RAIN": [src("RAIN")], "GAUGE": [src("GAUGE", variables=["discharge"], units={"discharge": "m3/s"})]}


def state(sources, evidence=None, cap=CAP):
    return rd.assess(cap, sources, CAT, evidence or {}, NOW)


def test_a_missing_essential_dataset_means_not_available_and_names_it():
    r = state({"RAIN": [src("RAIN")]})
    assert r["state"] == "NOT AVAILABLE" and r["next_requirement"] == "GAUGE: Gauges"


def test_wrong_units_mean_the_data_needs_processing_and_say_why():
    s = ok_sources()
    s["RAIN"] = [src("RAIN", units={"precipitation": "mm/day"})]
    r = state(s)
    assert r["state"] == "DATA AVAILABLE, PROCESSING REQUIRED" and r["next_requirement"] == "RAIN: Rainfall"
    bad = [c for c in r["checks"] if not c["ok"]]
    assert any(c["id"] == "RAIN.units" and "mm/day" in c["reason"] for c in bad)


@pytest.mark.parametrize("override, check", [
    ({"spatial_extent": [10.0, 10.0, 11.0, 11.0]}, "RAIN.space"),
    ({"time_extent": ["2021-01-01", "2026-10-31"]}, "RAIN.time"),
    ({"resolution_m": 25000}, "RAIN.resolution"),
    ({"crs": None}, "RAIN.crs"),
    ({"licence": None}, "RAIN.licence"),
    ({"licence": "Not stated on the portal"}, "RAIN.licence"),
    ({"variables": ["temperature"]}, "RAIN.variables"),
])
def test_each_condition_can_fail_on_its_own(override, check):
    s = ok_sources()
    s["RAIN"] = [src("RAIN", **override)]
    r = state(s)
    failed = {c["id"] for c in r["checks"] if not c["ok"]}
    assert check in failed and r["state"] == "DATA AVAILABLE, PROCESSING REQUIRED"


def test_fit_data_still_needs_a_model_and_then_each_rung_in_turn():
    s = ok_sources()
    assert state(s)["state"] == "MODEL REQUIRED"
    ev = {"flood.X.model": {"summary": "m"}}
    assert state(s, ev)["state"] == "CALIBRATION REQUIRED"
    ev["flood.X.calibration"] = {"summary": "c"}
    assert state(s, ev)["state"] == "VALIDATION REQUIRED"
    ev["flood.X.validation"] = {"summary": "v", "needsDatasets": ["GAUGE"]}
    assert state(s, ev)["state"] == "EXPERIMENTAL"
    ev["flood.X.operational"] = {"summary": "o"}
    assert state(s, ev)["state"] == "OPERATIONALLY EVALUATED"


def test_a_validation_record_without_its_validation_data_does_not_count():
    ev = {"flood.X.model": {}, "flood.X.calibration": {}, "flood.X.validation": {"needsDatasets": ["INDEPENDENT"]}}
    assert state(ok_sources(), ev)["state"] == "VALIDATION REQUIRED"


def test_a_ceiling_is_never_exceeded():
    ev = {k: {} for k in ("flood.X.model", "flood.X.calibration", "flood.X.validation", "flood.X.operational")}
    assert state(ok_sources(), ev, {**CAP, "ceiling": "VALIDATION REQUIRED"})["state"] == "VALIDATION REQUIRED"


def test_optional_data_is_listed_as_partial_without_blocking():
    r = state(ok_sources())
    assert r["partial"] == ["SOIL: Soil"] and r["state"] == "MODEL REQUIRED"


def test_context_capabilities_stop_at_their_data():
    cap = {**CAP, "context": True}
    assert state(ok_sources(), cap=cap)["state"] == rd.CONTEXT
    assert state({"RAIN": [src("RAIN")]}, cap=cap)["state"] == "NOT AVAILABLE"


def test_freshness_uses_available_at():
    need = {**RAIN, "name": "Rainfall", "freshDays": 2}
    fresh = rd.check_dataset(need, src("RAIN"), CAT["areas"], CAT["windows"], NOW)
    stale = rd.check_dataset(need, src("RAIN", available_at="2026-10-01T00:00:00Z"), CAT["areas"], CAT["windows"], NOW)
    assert next(c for c in fresh if c["id"] == "RAIN.fresh")["ok"]
    assert not next(c for c in stale if c["id"] == "RAIN.fresh")["ok"]


def test_the_best_copy_of_a_dataset_is_used():
    s = ok_sources()
    s["RAIN"] = [src("RAIN", units={"precipitation": "mm/day"}), src("RAIN")]
    assert state(s)["state"] == "MODEL REQUIRED"


def test_source_files_are_round_tripped_and_refuse_unknown_fields(tmp_path):
    rd.write_source(tmp_path / "raw/met/x", dataset="RAIN", licence="CC BY 4.0", crs="EPSG:4326")
    loaded = rd.load_sources(tmp_path)
    assert list(loaded) == ["RAIN"] and loaded["RAIN"][0]["licence"] == "CC BY 4.0"
    with pytest.raises(ValueError):
        rd.write_source(tmp_path / "y", dataset="RAIN", colour="blue")
    with pytest.raises(ValueError):
        rd.write_source(tmp_path / "z", licence="x")


def _register():
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).resolve().parents[2] / "processing/scripts/register_source.py"
    spec = importlib.util.spec_from_file_location("register_source", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_register_source_reads_extent_and_time_from_a_table_and_lets_arguments_win(tmp_path):
    folder = tmp_path / "raw/hydro/dhm/discharge"
    folder.mkdir(parents=True)
    (folder / "betrawati.csv").write_text("date,lon,lat,discharge\n2014-06-01,85.18,27.97,410\n2024-09-28,85.18,27.97,1960\n", encoding="utf-8")
    _register().main([str(folder), "--dataset", "B2", "--licence", "By request", "--units", "discharge=m3/s", "--available-at", "2026-11-01T00:00:00Z"])
    meta = rd.load_sources(tmp_path)["B2"][0]
    assert meta["time_extent"] == ["2014-06-01", "2024-09-28"]
    assert meta["spatial_extent"] == [85.18, 27.97, 85.18, 27.97] and meta["crs"] == "EPSG:4326"
    assert meta["variables"] == ["discharge"] and meta["units"] == {"discharge": "m3/s"}
    assert meta["licence"] == "By request" and meta["available_at"] == "2026-11-01T00:00:00Z"


def test_register_source_reads_a_geotiff(tmp_path):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    folder = tmp_path / "raw/lc/esa/worldcover"
    folder.mkdir(parents=True)
    with rasterio.open(folder / "lc.tif", "w", driver="GTiff", width=10, height=10, count=1, dtype="uint8", crs="EPSG:32645",
                       transform=from_origin(340000, 3130000, 10, 10)) as d:
        d.write(np.ones((1, 10, 10), np.uint8))
    _register().main([str(folder), "--dataset", "C3", "--licence", "CC BY 4.0"])
    meta = rd.load_sources(tmp_path)["C3"][0]
    assert meta["crs"] == "EPSG:32645" and meta["resolution_m"] == 10.0
    w, s, e, n = meta["spatial_extent"]
    assert 84 < w < e < 86 and 27 < s < n < 29


def test_a_validation_that_missed_its_own_criterion_does_not_count_and_says_so():
    ev = {"flood.X.model": {}, "flood.X.calibration": {}, "flood.X.validation": {"summary": "CSI 0.04, chance 0.05", "criterionMet": False}}
    r = state(ok_sources(), ev)
    assert r["state"] == "VALIDATION REQUIRED"
    check = next(c for c in r["checks"] if c["id"] == "flood.X.validation")
    assert not check["ok"] and check["reason"].startswith("Ran, and missed its criterion: CSI 0.04")
    ev["flood.X.validation"]["criterionMet"] = True
    assert state(ok_sources(), ev)["state"] == "EXPERIMENTAL"
