"""LANDMET logic on tiny inputs, then on the real file when it is present in data/raw/landmet."""
import json
import pathlib

import h5py
import numpy as np
import pytest
import rasterio

from cascade_lens import landmet, quality

ROOT = pathlib.Path(__file__).resolve().parents[2]
REAL = next(iter((ROOT / "data/raw/landmet").glob("*.nc")), None)
ZONES = np.array([3] + [360] * 178 + [9], np.int16)


def test_cell_grid_covers_every_cell_with_north_up_and_west_left():
    g = landmet.cell_grid(ZONES)
    assert g.shape == (180, 360) and set(np.unique(g)) == set(range(ZONES.sum()))
    assert g[179, 180] == 0, "southern zone starts at 0 E, column 180"
    assert g[179, 0] == 1, "180 W is lon 180 in the file's 0 to 360 system, the second of three cells"
    assert g[0, 180] == ZONES[:-1].sum(), "the northern zone is the top row"


def test_scale_key_comes_from_the_variable_not_a_convention(tmp_path):
    with h5py.File(tmp_path / "x.nc", "w") as f:
        a = f.create_dataset("a", data=np.array([[100, -9999]], np.int16))
        a.attrs["_FillValue"] = [-9999]
        a.attrs["scale"] = [0.01]
        got = landmet.read_cells(f["a"], dict(scale="scale"), 0)
        unscaled = landmet.read_cells(f["a"], dict(scale=None), 0)
    assert abs(got[0] - 1) < 1e-6 and np.isnan(got[1]) and unscaled[0] == 100


def test_implausible_values_are_flagged_not_changed():
    v = np.array([5, 118.6, np.nan], np.float32)
    assert landmet.classify(v, (0, 60)).tolist() == [quality.VALID, quality.MASKED, quality.NODATA]
    assert v[1] == pytest.approx(118.6)


def test_diurnal_check_finds_a_planted_peak():
    utc = np.arange(0, 24, 3.0)
    lon = np.array([0.0, 90.0])
    lat = np.array([0.0, 10.0])
    temp = np.zeros((8, 2))
    temp[4, 0] = 10  # 12 UTC at 0 E is 12 local
    temp[2, 1] = 10  # 06 UTC at 90 E is 12 local
    assert landmet.diurnal_peak_local_hour(temp, lat, lon, utc) == 12


real = pytest.mark.skipif(REAL is None, reason="LANDMET file not in data/raw/landmet")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    d = tmp_path_factory.mktemp("lm")
    return landmet.prepare(REAL, d / "public/data", d / "w", d / "qa"), d


@real
def test_real_grid_puts_each_pixel_inside_its_own_cell():
    with h5py.File(REAL) as f:
        lat, lon, zones = f["eqlat"][()], f["eqlon"][()], f["eqcells_in_zone"][()]
    g = landmet.cell_grid(zones)
    rows, cols = np.mgrid[0:180, 0:360]
    plat, plon = 89.5 - rows, (cols - 179.5) % 360
    assert np.abs(lat[g] - plat).max() < 0.51
    diff = np.abs((lon[g] - plon + 180) % 360 - 180)
    assert (diff <= 180 / zones[np.floor(plat).astype(int) + 90] + 0.51).all()


@real
def test_real_values_round_trip_to_the_source_cell(built):
    m, d = built
    layer = next(x for x in m["layers"] if x["id"] == "landmet:skin-temp")
    with h5py.File(REAL) as f:
        i = int(np.argmin(np.abs(f["eqlat"][()] - 23.5) + np.abs(f["eqlon"][()] - 10.5)))
        expected = f["FDtemps"][4, i] * 0.1
        lat, lon = float(f["eqlat"][i]), float(f["eqlon"][i])
    with rasterio.open(d / "public" / layer["timeSteps"][4]["sources"][0]["sampling"]) as c:
        got = next(c.sample([(lon, lat)]))[0]
    assert got == pytest.approx(expected, abs=0.01)


@real
def test_real_file_passes_the_physics_check(built):
    assert 11.5 < built[0]["qa"]["diurnalPeakLocalHour"] < 15.5, "the daily peak must fall near local afternoon, or time or longitude is wrong"


@real
def test_real_empty_variables_are_shown_as_unavailable(built):
    m, _ = built
    empty = [x for x in m["layers"] if x["status"] == "unavailable"]
    assert len(empty) >= 5 and all("fill" in x["statusReason"] and not x["sources"] for x in empty)


@real
def test_real_impossible_wind_is_flagged(built):
    q = built[0]["qa"]["variables"]["ISDwspeed"]
    assert q["max"] > 100 and q["maskedCells"] > 0


@real
def test_real_case_cannot_be_mistaken_for_rasuwa(built):
    m, _ = built
    assert m["fixture"] and "not NISAR" in m["fixtureLabel"]
    assert all(x["mission"] == "LANDMET" for x in m["layers"]) and not m["groups"]
    assert json.dumps(m).count("Rasuwa") >= 1 and all(any("not NISAR" in t for t in x["limitations"]) for x in m["layers"])
