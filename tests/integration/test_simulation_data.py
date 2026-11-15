"""The Simulate mode's shipped data must follow the rivers and never run uphill."""
import json
import pathlib

DATA = json.loads((pathlib.Path(__file__).resolve().parents[2] / "frontend/public/data/vectors/simulation.json").read_text(encoding="utf8"))


def test_path_runs_from_the_mapped_source_down_past_the_named_places():
    lng, lat, top = DATA["path"][0]
    assert 85.51 < lng < 85.53 and 28.28 < lat < 28.30  # Inside the UNOSAT detachment zone's bounds
    assert top > DATA["path"][-1][2] + 3000
    order = {p["name"]: p["km"] for p in DATA["places"]}
    assert order["Rasuwa Gadhi"] < order["Shyaphru Bensi"] < order["Betrawati"] < order["Trishuli"] < order["Mugling"]


def test_river_level_never_rises_downstream():
    levels = [p[2] for p in DATA["path"]]
    assert all(a >= b for a, b in zip(levels, levels[1:]))


def test_nearly_every_mapped_building_lies_along_the_path():
    assert DATA["totals"]["buildings"] / DATA["totals"]["buildingsAll"] > 0.95
