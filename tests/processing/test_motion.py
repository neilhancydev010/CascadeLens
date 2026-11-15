"""Glacial-lake pair products on synthetic files (invented values, not NASA data).

The coherence layer is the only part that reaches the app. The dam and glacier bounds are research only, and must refuse
rather than guess when an input is missing or too thin."""
import json

import h5py
import numpy as np
import pytest
from rasterio.transform import from_origin

from cascade_lens import motion

X0, Y0, N, P = 500000.0, 3085000.0, 100, 80.0  # 8 km square in UTM 45N
DAM = (X0 + 50 * P, Y0 - 50 * P)
NAME = "NISAR_L2_PR_GUNW_028_048_D_074_029_2000_SH_20260816T125812_20260816T125846_20260828T125812_20260828T125846_P05023_N_F_J_001.h5"


def make_pair(path, cc=None, mask=None, centre_frequency=1257.5e6, wrapped=True):
    with h5py.File(path, "w") as f:
        root = f.create_group("/science/LSAR/GUNW/grids/frequencyA")
        if centre_frequency is not None:
            root["centerFrequency"] = centre_frequency
        u = root.create_group("unwrappedInterferogram")
        u["xCoordinates"], u["yCoordinates"] = X0 + np.arange(N) * P, Y0 - np.arange(N) * P
        hh = u.create_group("HH")
        hh["unwrappedPhase"] = np.full((N, N), 1.0, np.float32)
        hh["ionospherePhaseScreen"] = np.zeros((N, N), np.float32)
        hh["coherenceMagnitude"] = np.full((N, N), 0.8, np.float32)
        hh.create_dataset("connectedComponents", data=np.ones((N, N), np.uint16) if cc is None else cc).attrs["_FillValue"] = 65535
        u["mask"] = np.full((N, N), 11, np.uint8) if mask is None else mask
        if wrapped:
            w = root.create_group("wrappedInterferogram")
            w["xCoordinates"], w["yCoordinates"] = X0 + np.arange(40) * 20.0, Y0 - np.arange(40) * 20.0
            w["HH/coherenceMagnitude"] = np.full((40, 40), 0.6, np.float32)


def _dist():
    xx, yy = np.meshgrid(X0 + np.arange(N) * P, Y0 - np.arange(N) * P)
    return np.hypot(xx - DAM[0], yy - DAM[1])


def test_a_clean_case_gives_a_research_only_magnitude_bound(tmp_path):
    p = tmp_path / NAME
    make_pair(p)
    r = motion.dam_test(p, DAM)
    assert r["ok"] and r["researchOnly"] and r["refPixels"] >= motion.MIN_REF_PIXELS
    assert r["wavelengthM"] == pytest.approx(299_792_458.0 / 1257.5e6, abs=1e-5), "wavelength from the file's own centre frequency"
    assert r["magnitudeDifferenceCm"] == 0.0 and not r["exceedsTwiceSpread"]


def test_too_few_reference_pixels_cannot_succeed(tmp_path):
    p = tmp_path / NAME
    mask = np.full((N, N), 11, np.uint8)
    mask[_dist() > motion.REF_RING_M[0]] = 10  # the whole reference ring is an invalid subswath
    make_pair(p, mask=mask)
    r = motion.dam_test(p, DAM)
    assert not r["ok"] and "reference" in r["reason"]


def test_unreliable_labels_never_count(tmp_path):
    p = tmp_path / NAME
    cc = np.ones((N, N), np.uint16)
    cc[_dist() < motion.DAM_RADIUS_M] = 0  # the dam was not reliably unwrapped
    make_pair(p, cc=cc)
    r = motion.dam_test(p, DAM)
    assert not r["ok"] and "dam" in r["reason"]
    cc[_dist() < motion.DAM_RADIUS_M] = 65535
    make_pair(p, cc=cc)
    assert not motion.dam_test(p, DAM)["ok"], "the fill value is not a component either"


def test_no_stated_frequency_means_no_wavelength(tmp_path):
    p = tmp_path / NAME
    make_pair(p, centre_frequency=None)
    r = motion.dam_test(p, DAM)
    assert not r["ok"] and "frequency" in r["reason"]


def test_the_app_manifest_gets_coherence_and_never_movement(tmp_path):
    folder = tmp_path / "pairs"
    folder.mkdir()
    make_pair(folder / NAME)
    public, work = tmp_path / "public/data", tmp_path / "work"
    rows, cols = 20, 20
    grid = {"x0": X0, "y0": Y0, "rows": rows, "cols": cols, "posting": 20.0, "transform": from_origin(X0 - 10, Y0 + 10, 20, 20)}
    hh = {"id": "case:hh", "groupId": None, "mission": "NISAR", "instrument": "L-SAR", "crs": "EPSG:32645", "qualityLayerIds": [], "attribution": "a",
          "productMaturity": "Provisional", "postingM": [20, 20], "frames": [74], "track": 48, "orbitDirection": "DESCENDING"}
    m = {"caseStudy": {"searchEnvelope": [86.0, 27.8, 86.1, 27.9]}, "layers": [hh, {"id": "ref:zones"}], "lake": {"terrain": None, "motion": {"dam": {"limitCm": 1.6}}}}
    lake = np.zeros((rows, cols), bool)
    lake[5:10, 5:10] = True
    cfg = {"id": "case", "epsg": 32645, "track": 48, "frame": 74, "zoom": [10, 12]}
    out = motion.add_coherence_layer(m, cfg, [folder], public, work, grid, lake)
    assert "motion" not in out["lake"], "movement bounds are research only"
    assert "ref:zones" not in [l["id"] for l in out["layers"]]
    layer = next(l for l in out["layers"] if l["id"] == "case:coherence")
    assert layer["measurementType"] == "gunw-coherence" and "not a measurement of movement" in " ".join(layer["limitations"])
    assert out["lake"]["coherence"]["pair"] == ["2026-08-16", "2026-08-28"] and out["lake"]["coherence"]["lake"] == 0.6
    assert out["lake"]["coherence"]["maskApplied"] is False and json.dumps(out)
