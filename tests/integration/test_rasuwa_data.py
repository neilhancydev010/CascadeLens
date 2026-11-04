"""Real-data validation, section 21.4 of the brief: the prepared layers against the actual Rasuwa granules.

Skipped until the granules are in data/raw/nisar, because they need an Earthdata login.
"""
import json
import pathlib
import sys

import h5py
import numpy as np
import pytest
import rasterio
import rasterio.warp

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import nisar, pipeline, quality  # noqa: E402

CFG = json.loads((ROOT / "processing/configs/pipeline.json").read_text())
CAT = json.loads((ROOT / "data/metadata/catalogue.json").read_text())
M = json.loads((ROOT / "frontend/public/data/manifests/manifest.json").read_text(encoding="utf-8"))
RAW = ROOT / "data/raw"
GRANULES = [g for g in pipeline.select_granules(CAT, CFG) if pipeline.granule_path(RAW, g).exists()]
pytestmark = pytest.mark.skipif(not GRANULES, reason="no Rasuwa granules downloaded")
PHASE = [g for g in GRANULES if g["product"] == "GUNW"]


def layer(i):
    return next(x for x in M["layers"] if x["id"] == i)


@pytest.mark.parametrize("g", GRANULES, ids=lambda g: f"{g['product']}-{g['track']}-{g['frame']}")
def test_file_identity_matches_the_catalogue_and_brief(g):
    with h5py.File(pipeline.granule_path(RAW, g)) as f:
        i = nisar.identify(f)
    assert (i["trackNumber"], i["frameNumber"], i["productType"]) == (g["track"], g["frame"], g["product"])
    assert str(i["orbitPassDirection"]).upper() == g["direction"]
    assert i["referenceZeroDopplerStartTime"][:10] == g["ref_date"] and i["secondaryZeroDopplerStartTime"][:10] == g["sec_date"]
    assert i["compositeReleaseId"] == "P05023"


@pytest.mark.parametrize("g", GRANULES, ids=lambda g: f"{g['product']}-{g['track']}-{g['frame']}")
def test_every_granule_passes_inspection(g):
    r = nisar.inspect(pipeline.granule_path(RAW, g), g["product"], CFG["goff_layer"])
    assert r["missing"] == [] and r["unit_mismatch"] == []
    assert quality.passed(quality.check_granule(r, g))


def test_primary_pair_acquisitions_bracket_the_event():
    with h5py.File(pipeline.granule_path(RAW, PHASE[0])) as f:
        i = nisar.identify(f)
    assert i["referenceZeroDopplerStartTime"] < "2026-08-26" < i["secondaryZeroDopplerStartTime"]


def test_maturity_comes_from_the_real_files():
    assert layer("pair-a:gunw-phase")["productMaturity"] == "Provisional (P05023)"


@pytest.mark.parametrize("mid", ["gunw-phase", "gunw-coherence", "gunw-cc"])
def test_sampling_rasters_equal_the_source_arrays(mid):
    for s in layer(f"pair-a:{mid}")["sources"]:
        g = next(x for x in PHASE if x["file_id"] == s["granule"])
        w = s["clipWindow"]
        with h5py.File(pipeline.granule_path(RAW, g)) as f, rasterio.open(ROOT / "frontend/public" / s["sampling"]) as c:
            src = quality.clean(f[s["sourceDataset"]][w[0]:w[1], w[2]:w[3]], 65535 if mid == "gunw-cc" else None)
            assert np.array_equal(c.read(1), src, equal_nan=True)


def test_layers_overlap_the_independent_terrain_and_reference_data():
    bbox = CFG["aoi_bbox"]
    for s in layer("pair-a:gunw-coherence")["sources"]:
        w, so, e, n = s["bounds"]
        assert w < bbox[2] and e > bbox[0] and so < bbox[3] and n > bbox[1]


def test_coherence_is_normalised_and_valid_pixels_exist():
    for s in layer("pair-a:gunw-coherence")["sources"]:
        with rasterio.open(ROOT / "frontend/public" / s["sampling"]) as c:
            a = c.read(1)
        assert np.nanmin(a) >= 0 and np.nanmax(a) <= 1.0001 and s["validFraction"] > 0.2


def test_derived_phase_is_exactly_phase_minus_screen():
    for frame in ("f074", "f075"):
        d = ROOT / "data/processed/pair-a" / frame
        with rasterio.open(d / "gunw-phase.tif") as p, rasterio.open(d / "gunw-iono.tif") as i, rasterio.open(d / "gunw-phase-iono.tif") as o:
            assert np.array_equal(o.read(1), p.read(1) - i.read(1), equal_nan=True)


def test_subtracting_the_screen_is_the_right_direction():
    """The basis for the derived layer: subtraction must reduce scatter, and addition must raise it, in every frame."""
    for f in M["analysis"]["pair-a"]["frames"].values():
        i = f["ionosphere"]
        assert i["stdPhaseMinusIono"] < i["stdPhase"] < i["stdPhasePlusIono"]
