"""Checks the manifest and assets that actually ship with the app."""
import json
import os
import pathlib
import subprocess
import sys

import pytest
import rasterio
import rasterio.warp

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import manifest as mf  # noqa: E402

PUBLIC = ROOT / "frontend/public"
M = json.loads((PUBLIC / "data/manifests/manifest.json").read_text(encoding="utf-8"))


def test_assets_exist():
    assert mf.validate(M, PUBLIC) == []


def test_is_not_a_fixture_and_contains_no_synthetic_source():
    assert M["fixture"] is False
    assert "SYNTHETIC" not in json.dumps(M)


def test_nisar_layers_are_usable_only_with_processed_sources():
    for l in M["layers"]:
        if l["mission"] == "NISAR":
            assert (l["status"] in mf.USABLE) == bool(l["sources"]), l["id"]


def test_primary_pair_matches_the_project_specification():
    a = next(g for g in M["groups"] if g["id"] == "pair-a")
    assert (a["reference"], a["secondary"], a["direction"], a["track"], a["frames"]) == ("2026-08-16", "2026-08-28", "DESCENDING", 48, [74, 75])


def test_every_layer_keeps_attribution_and_limits():
    for l in M["layers"]:
        assert l["attribution"] and l["limitations"] and l["mission"], l["id"]


def test_sentinels_of_source_separation():
    for l in M["layers"]:
        if l["category"] == "reference":
            assert l["mission"] != "NISAR" and l["measurementClass"] != "measurement"
    u = next(l for l in M["layers"] if l["id"] == "ref:unosat-extent")
    assert any("field validated" in t for t in u["limitations"])


def test_no_displacement_layer_exists():
    assert not [l for l in M["layers"] if "displacement" in l["id"].lower() or "los" in l["id"].lower()]


def test_catalogue_never_mixes_release_ids():
    assert all("_P05023_" in g["file_id"] for g in M["granules"])


def test_bookmarks_are_finite_and_have_a_basis():
    assert [b["id"] for b in M["bookmarks"]] == ["source", "bhote-koshi", "trishuli"]
    for b in M["bookmarks"]:
        w, s, e, n = b["bounds"]
        assert w < e and s < n and b["basis"]
        assert w <= b["anchor"]["lng"] <= e and s <= b["anchor"]["lat"] <= n and b["anchor"]["label"]


def test_colour_only_products_can_never_be_sampled():
    dpm = next(l for l in M["layers"] if l["id"] == "ref:eos-dpm")
    assert dpm["status"] == "renderable" and dpm["mission"] == "Sentinel-1"
    assert not any("sampling" in s for s in dpm["sources"])


def test_sentinel1_layers_never_claim_to_be_nisar():
    for l in M["layers"]:
        if l["mission"] == "Sentinel-1":
            assert any("Not NISAR" in t for t in l["limitations"]) or "analysed" in " ".join(l["limitations"]), l["id"]


def test_landmet_case_is_complete_and_clearly_labelled():
    path = PUBLIC / "data/manifests/landmet.json"
    lm = json.loads(path.read_text(encoding="utf-8"))
    assert mf.validate(lm, PUBLIC) == []
    assert lm["fixture"] is True and "not NISAR" in lm["fixtureLabel"]
    assert {l["mission"] for l in lm["layers"]} == {"LANDMET"}


def test_real_measurements_are_published_for_both_pairs():
    ids = {l["id"] for l in M["layers"] if l["status"] == "sampleable"}
    assert {"pair-a:gunw-phase", "pair-a:gunw-coherence", "pair-a:gunw-phase-iono", "pair-a:goff-range", "pair-b:goff-range"} <= ids
    assert next(l for l in M["layers"] if l["id"] == "pair-a:gunw-phase-iono")["measurementClass"] == "derived"
    assert not [l for l in M["layers"] if l["category"] == "preview"], "a picture never sits beside the real measurement"


def test_analysis_records_the_source_gap_and_pair_b_coverage():
    a, b = M["analysis"]["pair-a"]["frames"]["f074"], M["analysis"]["pair-b"]["frames"]["f016"]
    assert a["zones"]["gunw-coherence"]["detachment zone"]["validPct"] == 0
    assert b["zones"]["goff-peak"]["detachment zone"]["validPct"] == 100
    for f in M["analysis"]["pair-a"]["frames"].values():
        z = f["zones"]["gunw-coherence"]
        assert z["mapped extent"]["median"] < z["1 km ring outside extent"]["median"]


def test_download_without_credentials_stops_with_a_clear_message(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "EARTHDATA_TOKEN"} | {"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)}
    r = subprocess.run([sys.executable, str(ROOT / "processing/scripts/download_products.py"), "--qa-only"], capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode != 0 and "No Earthdata credentials found" in r.stderr and "Nothing was downloaded" in r.stderr


def test_a_malformed_token_is_refused_without_being_echoed(tmp_path):
    secret = 'copied "the wrong" thing'
    env = os.environ | {"USERPROFILE": str(tmp_path), "HOME": str(tmp_path), "EARTHDATA_TOKEN": secret}
    r = subprocess.run([sys.executable, str(ROOT / "processing/scripts/download_products.py"), "--qa-only"], capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode != 0 and "not an Earthdata token" in r.stderr and "Traceback" not in r.stderr
    assert secret not in r.stdout + r.stderr


def test_config_files_are_plain_ascii():
    """Windows reads files as cp1252 by default, and a stray en dash has already corrupted one of these once."""
    for p in (ROOT / "processing/configs").glob("*.json"):
        p.read_bytes().decode("ascii")


@pytest.mark.parametrize("key", ["sampling", "validity"])
def test_raster_metadata_matches_manifest(key):
    for l in M["layers"]:
        for s in l["sources"]:
            if key not in s:
                continue
            with rasterio.open(PUBLIC / s[key]) as d:
                assert f"EPSG:{d.crs.to_epsg()}" == l["crs"]
                b = rasterio.warp.transform_bounds(d.crs, "EPSG:4326", *d.bounds)
                assert all(abs(x - y) < 1e-6 for x, y in zip(b, s["bounds"]))
