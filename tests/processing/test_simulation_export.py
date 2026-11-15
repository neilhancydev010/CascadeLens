"""The What-if table written by export_simulation_features.py matches the app's data, and re-counts the three documented settings."""
import csv
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("export_sim", ROOT / "processing/scripts/export_simulation_features.py")
export_sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_sim)


def _table():
    with (ROOT / "data/qa/rasuwa-2026-simulation-features.csv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_table_is_the_shipped_simulation_data():
    sim = json.loads((ROOT / "frontend/public/data/vectors/simulation.json").read_text(encoding="utf8"))
    fresh = [[str(v) for v in r] for r in export_sim.rows(sim)]
    shipped = [[r[c] for c in export_sim.COLUMNS] for r in _table()]
    assert fresh == shipped


def test_three_documented_settings():
    t = _table()
    for rise, km, buildings, road, places in ((25, 198, 3274, 119.339, 8), (10, 74, 489, 11.305, 1), (50, 35, 553, 25.265, 2)):
        c = export_sim.count(t, km, rise)
        assert c["buildings"] == buildings
        assert round(c["roadKm"], 3) == road
        assert len(c["places"]) == places
