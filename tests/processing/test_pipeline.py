import json
import math

import h5py
import numpy as np
import pytest
import rasterio
from PIL import Image
from pyproj import Transformer

from cascade_lens import discovery, export, manifest, nisar, pipeline, quality
from conftest import AOI, EPSG, N, POST, X0, Y0, granule, make_gcov, make_gunw


def test_parse_real_granule_names():
    g = discovery.parse_file_id("NISAR_L2_PR_GUNW_029_026_A_016_031_4000_SH_20260826T234737_20260826T234812_20260919T234737_20260919T234812_P05023_F_F_J_001")
    assert (g["product"], g["track"], g["direction"], g["frame"]) == ("GUNW", 26, "ASCENDING", 16)
    assert (g["ref_date"], g["sec_date"]) == ("2026-08-26", "2026-09-19")
    c = discovery.parse_file_id("NISAR_L2_PR_GCOV_029_048_D_074_2000_SHNA_A_20260828T125846_20260828T125920_P05023_N_F_J_001")
    assert (c["ref_date"], c["sec_date"]) == ("2026-08-28", None)


def test_inspection_reports_metadata_and_datasets(gunw_file):
    r = nisar.inspect(gunw_file, "GUNW")
    assert r["identification"]["trackNumber"] == 48 and r["identification"]["compositeReleaseId"] == "P05023"
    assert r["polarizations"] == ["HH"] and r["missing"] == [] and r["mask_present"]
    p = nisar.dataset_path("gunw-phase", "HH")
    assert r["datasets"][p]["epsg"] == EPSG and r["datasets"][p]["posting_m"] == [POST, -POST]


def test_inspection_flags_missing_dataset_and_wrong_units(tmp_path):
    p = tmp_path / "x.h5"
    make_gunw(p)
    with h5py.File(p, "a") as f:
        del f[nisar.dataset_path("gunw-coherence", "HH")]
        f[nisar.dataset_path("gunw-phase", "HH")].attrs["units"] = "degrees"
    r = nisar.inspect(p, "GUNW")
    assert len(r["missing"]) == 1 and r["unit_mismatch"][0]["found"] == "degrees"
    assert not quality.passed(quality.check_granule(r, granule()))


def test_qa_rejects_catalogue_mismatch(gunw_file):
    r = nisar.inspect(gunw_file, "GUNW")
    assert quality.passed(quality.check_granule(r, granule()))
    bad = {**granule(), "track": 98}
    assert any(c["check"] == "track" and not c["ok"] for c in quality.check_granule(r, bad))
    assert not quality.passed(quality.check_granule(r, {**granule(), "sec_date": "2026-08-31"}))


def test_grid_transform_is_pixel_edge(gunw_file):
    with h5py.File(gunw_file) as f:
        g = nisar.find_grid(f, nisar.dataset_path("gunw-phase", "HH"))
    t = g.transform()
    assert (t.c, t.f) == (X0 - POST / 2, Y0 + POST / 2) and g.dy == -POST


def test_non_uniform_grid_is_refused(tmp_path):
    p = tmp_path / "x.h5"
    make_gunw(p)
    with h5py.File(p, "a") as f:
        x = f["/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/xCoordinates"]
        v = x[()]
        v[5] += 40
        x[...] = v
    with h5py.File(p) as f, pytest.raises(ValueError):
        nisar.find_grid(f, nisar.dataset_path("gunw-phase", "HH"))


def test_window_matches_aoi_and_detects_no_overlap(gunw_file):
    with h5py.File(gunw_file) as f:
        g = nisar.find_grid(f, nisar.dataset_path("gunw-phase", "HH"))
    assert nisar.bbox_to_window(g, AOI) == (slice(0, N), slice(0, N))
    assert nisar.bbox_to_window(g, [10, 10, 11, 11]) is None
    lon, lat = Transformer.from_crs(EPSG, 4326, always_xy=True).transform(g.x[10], g.y[20])
    rows, cols = nisar.bbox_to_window(g, [lon - 1e-4, lat - 1e-4, lon + 1e-4, lat + 1e-4])
    assert rows.start <= 20 < rows.stop and cols.start <= 10 < cols.stop


def test_clean_handles_fill_nan_inf():
    out = quality.clean(np.array([1.0, -9999.0, np.nan, np.inf, -np.inf]), -9999.0)
    assert out[0] == 1 and np.isnan(out[1:]).all()
    assert np.isnan(quality.clean(np.array([np.nan]), np.nan)).all()


def test_mask_decoding_follows_rev_e():
    d = quality.decode_gunw_mask(np.array([11, 111, 10, 1, 255, 0], np.uint8))
    assert d["water"].tolist() == [False, True, False, False, False, False]
    assert d["invalid_subswath"].tolist() == [False, False, True, True, False, True]
    assert d["fill"].tolist() == [False, False, False, False, True, False]


def test_gunw_validity_classes():
    v = np.ones((1, 5), np.float32)
    v[0, 4] = np.nan
    out = quality.gunw_validity(v, np.array([[11, 111, 10, 255, 11]], np.uint8), np.array([[1, 1, 1, 1, 1]], np.uint16))
    assert out.tolist() == [[quality.VALID, quality.MASKED, quality.MASKED, quality.NODATA, quality.NODATA]]
    cc = quality.gunw_validity(np.ones((1, 3), np.float32), None, np.array([[0, 65535, 2]], np.uint16))
    assert cc.tolist() == [[quality.MASKED, quality.NODATA, quality.VALID]], "ATBD 5.9.1.7: label 0 was not reliably unwrapped"
    assert quality.gunw_validity(np.ones((1, 1), np.float32), None).tolist() == [[quality.VALID]], "coherence takes no component rule"


def test_gross_outliers_keep_real_signal_scale():
    a = np.random.default_rng(0).normal(0, 1, 10000).astype(np.float32)
    a[0], a[1] = 200, 5
    o = quality.gross_outliers(a, 10)
    assert o[0] and not o[1]
    assert not quality.gross_outliers(np.ones(5, np.float32), 10).any()


def test_snr_filter_only_when_configured():
    a = np.zeros((1, 3), np.float32) + np.array([1, 1, np.nan], np.float32)
    assert quality.offset_validity(a, None).tolist() == [[1, 1, 0]]
    snr = np.array([[9, 1, 9]], np.float32)
    assert quality.offset_validity(a, None, snr, 5).tolist() == [[1, 2, 0]]


def test_goff_mask_is_applied():
    a = np.ones((1, 3), np.float32)
    assert quality.offset_validity(a, None, mask=np.array([[11, 111, 255]], np.uint8)).tolist() == [[1, 2, 0]]


def test_gcov_mask_zero_needs_the_applied_flag():
    a = np.ones((1, 3), np.float32)
    m = np.array([[1, 0, 255]], np.uint8)
    assert quality.gcov_validity(a, m, True).tolist() == [[1, 2, 0]]
    assert quality.gcov_validity(a, m, False).tolist() == [[1, 1, 0]], "without the flag 0 carries no meaning"


def test_unit_names_are_synonyms_only_for_dimensionless():
    assert nisar.units_match("1", "unitless") and nisar.units_match("radians", "radians") and not nisar.units_match("radians", "1")


def test_native_zoom_stops_at_the_data_resolution():
    assert pipeline.native_zoom(80, 28, 12) == 11
    assert pipeline.native_zoom(20, 28, 12) == 12, "capped"
    assert pipeline.native_zoom(20, 28, 13) == 13


def test_gcov_end_to_end_keeps_linear_and_tiles_db(tmp_path, cfg):
    p = tmp_path / "gcov.h5"
    make_gcov(p)
    g = granule("GCOV", group="gcov-0828")
    state, recs = pipeline.process_granule(g, p, cfg, tmp_path / "w", tmp_path / "qa")
    assert state["status"] == "qa_passed" and [r["measurement"] for r in recs] == ["gcov-backscatter"]
    with rasterio.open(recs[0]["tif"]) as t, rasterio.open(recs[0]["validity"]) as v:
        a, cls = t.read(1), v.read(1)
    assert abs(a[10, 10] - 0.01) < 1e-7, "the stored raster stays linear"
    assert cls[5, 5] == quality.MASKED and cls[6, 6] == quality.NODATA and cls[0, 0] == quality.NODATA
    f = pipeline.finalize_layer("gcov-backscatter", recs, cfg, tmp_path / "public/data", tmp_path / "prep")
    assert f["displayDb"] and abs(f["stats"]["median"] + 20) < 1e-4, "statistics and legend are in dB"
    assert f["provenance"]["displayTransform"] == "10*log10"


def test_fragment_records_provenance(tmp_path, gunw_file, cfg):
    _, recs = pipeline.process_granule(granule(), gunw_file, cfg, tmp_path / "w", tmp_path / "qa")
    f = pipeline.finalize_layer("gunw-phase", [next(r for r in recs if r["measurement"] == "gunw-phase")], cfg, tmp_path / "public/data", tmp_path / "prep")
    s, p = f["sources"][0], f["provenance"]
    assert s["sourceDtype"] == "float32" and s["clipWindow"] == [0, N, 0, N] and s["sha256"] and s["maskedFraction"] > 0
    assert p["pipelineVersion"] and len(p["configSha256"]) == 64 and p["outputDtype"] == "float32" and p["tileResampling"] == "nearest" and "label 0" in p["maskRule"]


def test_mismatched_grids_are_refused(tmp_path, cfg, gunw_file, monkeypatch):
    real = nisar.find_grid

    def shifted(h5, ds_path):
        g = real(h5, ds_path)
        return nisar.Grid(g.epsg, g.x + 40, g.y) if ds_path.endswith("coherenceMagnitude") else g

    monkeypatch.setattr(nisar, "find_grid", shifted)
    s, r = pipeline.process_granule(granule(), gunw_file, cfg, tmp_path / "w", tmp_path / "qa")
    assert s["status"] == "invalid" and "grid" in s["reason"] and not r


def test_db_conversion():
    out = quality.to_db(np.array([1, 0.1, 0, -1, np.nan], np.float32))
    assert out[0] == 0 and abs(out[1] + 10) < 1e-5 and np.isnan(out[2:]).all()


def test_tile_range_uses_xyz_not_tms():
    assert export.tile_range([0.1, 0.1, 0.2, 0.2], 1) == (1, 0, 1, 0)
    assert export.tile_range([0.1, -0.2, 0.2, -0.1], 1) == (1, 1, 1, 1)


def test_colorize_nan_is_transparent_and_consistent():
    rgba = export.colorize(np.array([[0, 1, np.nan]], np.float32), ["#000000", "#ffffff"], 0, 1)
    assert rgba[0, 0].tolist() == [0, 0, 0, 255] and rgba[0, 1].tolist() == [255, 255, 255, 255] and rgba[0, 2, 3] == 0


def test_pipeline_end_to_end_preserves_values(tmp_path, gunw_file, goff_file, cfg):
    g = granule("GUNW")
    state, recs = pipeline.process_granule(g, gunw_file, cfg, tmp_path / "w", tmp_path / "qa")
    assert state["status"] == "qa_passed" and len(recs) == 5
    phase = next(r for r in recs if r["measurement"] == "gunw-phase")
    with rasterio.open(phase["tif"]) as t, rasterio.open(phase["validity"]) as v, h5py.File(gunw_file) as f:
        src = f[nisar.dataset_path("gunw-phase", "HH")][()]
        a, cls = t.read(1), v.read(1)
        assert t.crs.to_epsg() == EPSG and t.transform.a == POST
        assert a[10, 10] == src[10, 10], "stored raster must keep the original numbers"
        assert np.isnan(a[0, 0]) and np.isnan(a[1, 1])
        assert cls[0, 0] == quality.NODATA and cls[2, 2] == quality.NODATA and cls[6, 6] == quality.NODATA
        assert cls[4, 4] == quality.MASKED and cls[5, 5] == quality.MASKED and cls[10, 10] == quality.VALID
        assert cls[3, 3] == quality.MASKED, "component label 0"
        assert a[4, 4] == src[4, 4], "masked pixels keep their value"
    pub, prep = tmp_path / "public/data", tmp_path / "prep"
    frag = pipeline.finalize_layer("gunw-phase", [phase], cfg, pub, prep)
    s = frag["sources"][0]
    assert frag["stats"]["displayMin"] == -frag["stats"]["displayMax"] or frag["stats"]["displayMin"] < 0
    with rasterio.open(tmp_path / "public" / s["sampling"]) as c:
        assert c.read(1)[10, 10] == a[10, 10] and c.profile["tiled"]

    gs, grecs = pipeline.process_granule(granule("GOFF"), goff_file, cfg, tmp_path / "w", tmp_path / "qa")
    assert gs["status"] == "qa_passed"
    rng = next(r for r in grecs if r["measurement"] == "goff-range")
    with rasterio.open(rng["tif"]) as t, rasterio.open(rng["validity"]) as v:
        assert t.read(1)[10, 10] == 500 and v.read(1)[10, 10] == quality.MASKED


def test_tiles_land_on_the_right_ground_location(tmp_path, gunw_file, cfg):
    """A tile pixel must show the raster pixel under it, checked through the mercator round trip."""
    _, recs = pipeline.process_granule(granule(), gunw_file, cfg, tmp_path / "w", tmp_path / "qa")
    rec = next(r for r in recs if r["measurement"] == "gunw-coherence")
    frag = pipeline.finalize_layer("gunw-coherence", [rec], cfg, tmp_path / "public/data", tmp_path / "prep")
    z = cfg["tile_zoom"][1]
    lon, lat = Transformer.from_crs(EPSG, 4326, always_xy=True).transform(X0 + 30 * POST, Y0 - 30 * POST)
    n = 2 ** z
    fx, fy = (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    tile = tmp_path / "public" / frag["sources"][0]["tiles"]["url"].format(z=z, x=int(fx), y=int(fy))
    assert tile.exists()
    px = np.array(Image.open(tile))[int((fy % 1) * 256), int((fx % 1) * 256)]
    want = export.colorize(np.array([[0.7]], np.float32), frag["stops"], 0, 1)[0, 0]
    assert px.tolist() == want.tolist()
    outside = lon - 1
    fx2 = (outside + 180) / 360 * n
    assert not (tile.parents[1] / str(int(fx2))).exists()


def test_no_data_class_survives_the_tile_warp(tmp_path):
    """Finite values in class 0 must stay hidden. Found on real data, where swath gaps hold finite phase with a fill mask."""
    size = 40
    tr = rasterio.Affine(80, 0, X0, 0, -80, Y0)
    values = np.full((size, size), 1.0, np.float32)
    validity = np.full((size, size), quality.NODATA, np.uint8)
    validity[:, size // 2:] = quality.VALID
    tif = export.write_geotiff(tmp_path / "v.tif", values, tr, EPSG)
    vtif = export.write_geotiff(tmp_path / "c.tif", validity, tr, EPSG, nodata=255)
    grid, _, _ = export.warp_to_tile_grid(tif, 12, validity_path=vtif)
    assert np.isfinite(grid).any()
    shown = np.isfinite(grid).sum()
    ground = (size // 2) * size * (80 / (2 * export.ORIGIN / (256 * 2 ** 12) * math.cos(math.radians(28.2)))) ** 2
    assert 0.8 * ground < shown < 1.2 * ground, "only the valid half may render"


def test_pipeline_is_reproducible(tmp_path, gunw_file, cfg):
    digests = []
    for run in ("a", "b"):
        d = tmp_path / run
        _, recs = pipeline.process_granule(granule(), gunw_file, cfg, d / "w", d / "qa")
        rec = next(r for r in recs if r["measurement"] == "gunw-phase")
        f = pipeline.finalize_layer("gunw-phase", [rec], cfg, d / "public/data", d / "prep")
        digests.append((export.sha256(rec["tif"]), export.sha256(d / "public" / f["sources"][0]["sampling"]), f["stats"]["displayMax"]))
    assert digests[0] == digests[1]


def test_derived_phase_subtracts_the_screen_and_keeps_stricter_validity(tmp_path, gunw_file, cfg):
    _, recs = pipeline.process_granule(granule(), gunw_file, cfg, tmp_path / "w", tmp_path / "qa")
    by = {r["measurement"]: r for r in recs}
    with rasterio.open(by["gunw-phase"]["tif"]) as p, rasterio.open(by["gunw-phase-iono"]["tif"]) as d, rasterio.open(by["gunw-phase-iono"]["validity"]) as v, h5py.File(gunw_file) as f:
        src = f[nisar.dataset_path("gunw-phase", "HH")][()]
        assert abs(d.read(1)[10, 10] - (p.read(1)[10, 10] - 0.5)) < 1e-6, "minus the 0.5 rad fixture screen"
        assert (src[10, 10] - p.read(1)[10, 10]) == 0, "the source phase layer is unchanged"
        cls = v.read(1)
    assert cls[3, 3] == quality.MASKED and cls[0, 0] == quality.NODATA
    assert "minus ionospherePhaseScreen" in by["gunw-phase-iono"]["dataset"]


def test_phase_like_layers_are_shown_relative_to_each_frame(tmp_path, cfg):
    """Frames are unwrapped separately: real Pair A frames sit about 50 radians apart, which would wash out a shared scale."""
    recs = []
    for fr, shift in ((74, 0.0), (75, 50.0)):
        p = tmp_path / f"{fr}.h5"
        make_gunw(p, frame=fr)
        with h5py.File(p, "a") as f:
            d = f[nisar.dataset_path("gunw-phase", "HH")]
            d[...] = d[()] + shift
        _, r = pipeline.process_granule(granule(frame=fr), p, cfg, tmp_path / "w", tmp_path / "qa")
        recs.append(next(x for x in r if x["measurement"] == "gunw-phase"))
    f = pipeline.finalize_layer("gunw-phase", recs, cfg, tmp_path / "public/data", tmp_path / "prep")
    assert f["displayRelative"] and f["stats"]["displayMax"] < 10, "the 50 radian step must not set the range"
    assert abs(f["sources"][1]["displayOffset"] - f["sources"][0]["displayOffset"] - 50) < 1e-3
    with rasterio.open(recs[1]["tif"]) as t:
        assert t.read(1)[10, 10] > 40, "stored values stay absolute"


def test_frames_stay_separate_with_shared_range(tmp_path, cfg):
    recs = []
    for fr in (74, 75):
        p = tmp_path / f"{fr}.h5"
        make_gunw(p, frame=fr)
        _, r = pipeline.process_granule(granule(frame=fr), p, cfg, tmp_path / "w", tmp_path / "qa")
        recs.append(next(x for x in r if x["measurement"] == "gunw-phase"))
    f = pipeline.finalize_layer("gunw-phase", recs, cfg, tmp_path / "public/data", tmp_path / "prep")
    assert [s["frame"] for s in f["sources"]] == [74, 75] and f["sources"][0]["sampling"] != f["sources"][1]["sampling"]


def test_no_overlap_and_failed_qa_produce_no_outputs(tmp_path, gunw_file, cfg):
    far = {**cfg, "aoi_bbox": [10, 10, 11, 11]}
    s, r = pipeline.process_granule(granule(), gunw_file, far, tmp_path / "w", tmp_path / "qa")
    assert s["status"] == "unavailable" and not r
    s, r = pipeline.process_granule({**granule(), "track": 98}, gunw_file, cfg, tmp_path / "w", tmp_path / "qa")
    assert s["status"] == "invalid" and not r


def test_select_granules_never_mixes_releases(cfg):
    base = {"product": "GOFF", "track": 48, "frame": 74, "direction": "DESCENDING", "ref_date": "2026-08-16", "sec_date": "2026-08-28", "url": None, "size_mb": 1}
    cat = [{**base, "file_id": "A_X05026_N_F_J_001"}, {**base, "file_id": "A_P05023_N_F_J_001"}]
    assert [g["file_id"] for g in pipeline.select_granules(cat, cfg)] == ["A_P05023_N_F_J_001"]


def test_manifest_status_comes_from_disk_not_config(tmp_path, cfg):
    root = tmp_path
    (root / "data/metadata/prepared").mkdir(parents=True)
    (root / "data/raw/nisar").mkdir(parents=True)
    cat = [{**granule("GUNW", f), "file_id": f"X_{f}_P05023_N"} for f in (74, 75)]
    (root / "data/metadata/catalogue.json").write_text(json.dumps(cat))
    m = manifest.build(root, cfg)
    phase = next(l for l in m["layers"] if l["id"] == "pair-a:gunw-phase")
    assert phase["status"] == "catalogued" and not phase["sources"] and "Earthdata" in phase["statusReason"]
    assert not m["groups"][0]["available"]
    (root / "data/raw/nisar" / "X_74_P05023_N.h5").write_bytes(b"")
    m = manifest.build(root, cfg)
    assert next(l for l in m["layers"] if l["id"] == "pair-a:gunw-phase")["status"] == "catalogued", "worst frame sets the status"
    goff = next(l for l in m["layers"] if l["id"] == "pair-a:goff-range")
    assert goff["status"] == "unavailable"


def test_manifest_validate_catches_missing_assets(tmp_path):
    m = {"layers": [{"id": "a", "status": "sampleable", "sources": [{"sampling": "data/x.tif", "validity": None}]},
                    {"id": "b", "status": "catalogued", "sources": [{"sampling": "y"}]},
                    {"id": "c", "status": "prepared", "sources": [], "vector": {"url": "data/z.geojson"}}]}
    errs = manifest.validate(m, tmp_path)
    assert errs == ["a: missing data/x.tif", "b: status catalogued but has sources", "b: missing y", "c: missing data/z.geojson"]
