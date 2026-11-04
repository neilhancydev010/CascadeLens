"""Run the code on NASA's public NISAR sample granules: real product structure, 2008 ALOS-derived scenes over California.

This proves the readers, not the science: no Rasuwa data is involved, and these files use an older release (D00404) than the
P05023 products. Skipped until `python processing/scripts/fetch_samples.py` has run.
"""
import pathlib
import subprocess
import sys

import h5py
import numpy as np
import pytest
import rasterio
from PIL import Image
from pyproj import Transformer

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import discovery, manifest, nisar, pipeline, previews, quality  # noqa: E402

SAMPLES = ROOT / "data/raw/samples"
pytestmark = pytest.mark.skipif(not SAMPLES.exists(), reason="run processing/scripts/fetch_samples.py")


def path(product, suffix=".h5"):
    return next(p for p in (SAMPLES / product).glob(f"*{suffix}") if not p.name.endswith(".iso.xml"))


def record(product):
    f = path(product)
    return {**discovery.parse_file_id(f.stem), "file_id": f.stem, "group": "sample", "size_mb": None, "url": None}


@pytest.fixture(scope="module")
def cfg():
    lons, lats = zip(*previews.parse_kml_quad(path("GUNW", ".kml").read_text(encoding="utf-8")))
    return {"aoi_bbox": [min(lons), min(lats), max(lons), max(lats)], "crid": "D00404", "goff_layer": 3, "gross_outlier_mad_k": 10, "snr_min": None,
            "coherence_threshold": None, "min_valid_fraction": 0.01, "tile_zoom": [9, 12]}


@pytest.fixture(scope="module")
def processed(tmp_path_factory, cfg):
    out = {}
    for product in ("GUNW", "GOFF", "GCOV"):
        d = tmp_path_factory.mktemp(product)
        state, recs = pipeline.process_granule(record(product), path(product), cfg, d / "w", d / "qa")
        out[product] = (state, {r["measurement"]: r for r in recs}, d)
    return out


@pytest.mark.parametrize("product", ["GUNW", "GOFF", "GCOV"])
def test_every_expected_dataset_exists_with_its_units(product):
    r = nisar.inspect(path(product), product)
    assert r["missing"] == [] and r["unit_mismatch"] == [] and r["mask_present"]
    assert r["polarizations"] == ["HH"] and r["identification"]["productType"] == product


@pytest.mark.parametrize("product", ["GUNW", "GOFF", "GCOV"])
def test_quality_gates_pass_on_a_real_file(processed, product):
    state, recs, _ = processed[product]
    assert state["status"] == "qa_passed", state
    assert recs


def test_real_posting_and_crs(processed):
    phase = processed["GUNW"][1]["gunw-phase"]
    assert phase["posting_m"] == [80.0, 80.0] and phase["epsg"] == 32611
    assert processed["GCOV"][1]["gcov-backscatter"]["posting_m"] == [20.0, 20.0]


def test_phase_and_coherence_share_a_grid():
    with h5py.File(path("GUNW")) as f:
        a = nisar.find_grid(f, nisar.dataset_path("gunw-phase", "HH"))
        b = nisar.find_grid(f, nisar.dataset_path("gunw-coherence", "HH"))
        c = nisar.find_grid(f, nisar.ROOT["GUNW"] + "/unwrappedInterferogram/mask")
    assert a.same_as(b) and a.same_as(c)


def test_stored_values_match_the_source_file(processed):
    r = processed["GUNW"][1]["gunw-phase"]
    with rasterio.open(r["tif"]) as t, h5py.File(path("GUNW")) as f:
        a = t.read(1)
        w = r["clip_window"]
        src = f[nisar.dataset_path("gunw-phase", "HH")][w[0]:w[1], w[2]:w[3]]
    assert a.shape == src.shape and np.array_equal(a, src, equal_nan=True)


def test_component_label_zero_is_masked_only_for_phase(processed):
    with h5py.File(path("GUNW")) as f:
        cc = f[nisar.dataset_path("gunw-cc", "HH")][()]
    assert (cc == 0).sum() > 1000, "the sample must exercise this rule"
    rs = processed["GUNW"][1]
    with rasterio.open(rs["gunw-phase"]["validity"]) as v, rasterio.open(rs["gunw-coherence"]["validity"]) as c:
        w = rs["gunw-phase"]["clip_window"]
        clipped = cc[w[0]:w[1], w[2]:w[3]]
        phase, coh = v.read(1), c.read(1)
    assert (phase[clipped == 0] == quality.MASKED).all()
    assert (coh[clipped == 0] == quality.VALID).mean() > 0.99


def test_goff_mask_reaches_the_validity_raster(processed):
    r = processed["GOFF"][1]["goff-range"]
    with h5py.File(path("GOFF")) as f, rasterio.open(r["validity"]) as v:
        m = f[nisar.ROOT["GOFF"] + "/pixelOffsets/mask"][()]
        w = r["clip_window"]
        m, cls = m[w[0]:w[1], w[2]:w[3]], v.read(1)
    assert (cls[m == 255] == quality.NODATA).all()
    assert (cls[(m // 100) == 1] != quality.VALID).all()


def test_gcov_samples_report_masking_not_applied(processed):
    with h5py.File(path("GCOV")) as f:
        assert nisar.flag(f, nisar.GCOV_MASKING_FLAG) is False
    assert processed["GCOV"][0]["validFraction"]["gcov-backscatter"] > 0.5, "mask value 0 must not wipe out the scene"


def test_maturity_is_read_from_the_file_not_assumed(processed):
    assert manifest.maturity(processed["GUNW"][0]["identification"], "P05023") == "Beta (D00404)"
    assert "confirm from file" in manifest.maturity({}, "P05023")


def test_coherence_is_normalised(processed):
    with rasterio.open(processed["GUNW"][1]["gunw-coherence"]["tif"]) as t:
        a = t.read(1)
    assert np.nanmin(a) >= 0 and np.nanmax(a) <= 1


def test_tiles_and_cog_export_from_a_real_file(processed, cfg):
    _, recs, d = processed["GUNW"]
    f = pipeline.finalize_layer("gunw-phase", [recs["gunw-phase"]], cfg, d / "public/data", d / "prep")
    s = f["sources"][0]
    assert f["stats"]["count"] > 100000 and s["tiles"]["count"] > 0 and s["tiles"]["maxzoom"] == 11
    with rasterio.open(d / "public" / s["sampling"]) as cog, rasterio.open(recs["gunw-phase"]["tif"]) as t:
        assert cog.crs == t.crs and cog.transform == t.transform and np.array_equal(cog.read(1), t.read(1), equal_nan=True)


def test_browse_picture_lines_up_with_the_measured_data(tmp_path):
    """The KML corners must put the PNG where the HDF5 grid says it belongs. This is what lets a preview stand in."""
    with h5py.File(path("GUNW")) as f:
        g = nisar.find_grid(f, nisar.dataset_path("gunw-phase", "HH"))
    to_ll = Transformer.from_crs(g.epsg, 4326, always_xy=True)
    corners = [to_ll.transform(x, y) for x, y in ((g.x[0], g.y[-1]), (g.x[-1], g.y[-1]), (g.x[-1], g.y[0]), (g.x[0], g.y[0]))]
    quad = previews.parse_kml_quad(path("GUNW", ".kml").read_text(encoding="utf-8"))
    assert max(abs(a - b) for p, q in zip(corners, quad) for a, b in zip(p, q)) < 0.002
    png = next(p for p in (SAMPLES / "GUNW").glob("*.png"))
    t = previews.build_source(png, path("GUNW", ".kml"), tmp_path / "t", 9, 11)
    assert t["count"] > 0 and Image.open(next((tmp_path / "t").rglob("*.png"))).size == (256, 256)


def test_nisar_qa_summary_is_readable_and_failures_are_kept():
    q = quality.read_qa_summary(path("GUNW", "_QA_SUMMARY.csv"))
    assert q["checks"] > 20 and q["failed"] == ["Passes all `identification` group checks?"]
    assert 40 < q["percent_nan"]["GUNW_L_A_unwrappedInterferogram_HH_unwrappedPhase"] < 41


def test_inspect_script_runs_on_a_real_file(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "processing/scripts/inspect_products.py"), str(path("GOFF"))], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "missing: 0 unit mismatches: 0" in r.stdout
