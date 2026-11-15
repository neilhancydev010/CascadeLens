"""A second viewing direction (another track) beside the main one: compared, never merged. Synthetic values, not NASA data."""
import importlib.util
import pathlib

import numpy as np
import pytest

from cascade_lens import manifest, observability as ob, pipeline

ROOT = pathlib.Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "processing/scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_compare_counts_only_usable_and_adds_up():
    # 8 cells in the zone: this view usable on 0-3, the other on 2-5; 6-7 usable from neither (outside, not assessed)
    this = np.array([1, 1, 1, 1, 2, 5, 6, 3, 1])
    other = np.array([3, 4, 1, 1, 1, 1, 5, 6, 1])
    zone = np.array([True] * 8 + [False])
    c = ob.compare_usable(this, other, zone)
    assert c == {"pixels": 8, "onlyThis": 25.0, "onlyOther": 25.0, "both": 25.0, "either": 75.0, "neither": 25.0}


def test_outside_the_frame_and_not_assessed_never_count_as_usable_from_either_view():
    this = np.array([5, 6, 4, 3, 2])  # outside, not assessed, no valid data, hidden, not reliable
    c = ob.compare_usable(this, this.copy(), np.ones(5, bool))
    assert c["either"] == 0.0 and c["neither"] == 100.0


def test_views_on_different_grids_are_refused():
    with pytest.raises(ValueError):
        ob.compare_usable(np.ones((3, 3)), np.ones((3, 4)), np.ones((3, 3), bool))
    assert ob.compare_usable(np.ones(3), np.ones(3), np.zeros(3, bool)) == {"pixels": 0}


def test_a_pair_can_limit_a_product_to_the_frames_that_reach_the_study_area():
    cfg = {"pairs": [{"id": "pair-b", "direction": "ASCENDING", "track": 98, "frames": [15, 16], "framesByProduct": {"GUNW": [16]},
                      "ref_date": "2026-08-19", "sec_date": "2026-08-31", "products": ["GUNW", "GOFF"]}], "snapshots": []}
    frames = {g["product"]: g["frames"] for g in pipeline.groups(cfg)}
    assert frames == {"GUNW": [16], "GOFF": [15, 16]}


def test_a_view_fragment_sits_beside_the_main_block_and_never_replaces_it():
    merge = script("merge_observability").merge
    m = {"layers": [{"id": "x:observability-movement"}], "observability": {"track": 48}}
    frag = {"case": "x", "layers": [{"id": "x:observability-movement-t98"}], "observabilityViews": {"t98": {"track": 98}}}
    out = merge(frag, m)
    assert out["observability"] == {"track": 48}
    assert out["observabilityViews"] == {"t98": {"track": 98}}
    assert [l["id"] for l in out["layers"]] == ["x:observability-movement", "x:observability-movement-t98"]
    again = merge({"case": "x", "layers": [], "observabilityViews": {"t98": {"track": 98, "v": 2}}}, out)
    assert again["observabilityViews"] == {"t98": {"track": 98, "v": 2}} and again["observability"] == {"track": 48}


def test_regenerating_the_manifest_keeps_merged_blocks_and_their_layers():
    built = {"layers": [{"id": "pair-b:gunw-coherence"}, {"id": "pair-a:gunw-coherence"}], "groups": ["new"]}
    current = {"layers": [{"id": "pair-a:gunw-coherence", "old": True}, {"id": "x:observability-movement"}, {"id": "x:road-exposure"}],
               "groups": ["old"], "observability": {"track": 48}, "observabilityViews": {"t98": {}}, "hazards": {"h": 1}, "controlSeries": {"c": 1}}
    out = manifest.keep_merged(built, current)
    assert out["groups"] == ["new"]
    assert [l["id"] for l in out["layers"]] == ["pair-b:gunw-coherence", "pair-a:gunw-coherence", "x:observability-movement", "x:road-exposure"]
    assert "old" not in out["layers"][1]  # a layer the build produces is always the fresh one
    assert out["observability"] == {"track": 48} and out["observabilityViews"] == {"t98": {}} and out["hazards"] == {"h": 1}


def test_re_merging_a_layer_replaces_it_where_it_stands():
    merge = script("merge_observability").merge
    m = {"layers": [{"id": "a"}, {"id": "x:coherence-timeline", "v": 1}, {"id": "x:coherence-timeline-t98"}]}
    out = merge({"case": "x", "layers": [{"id": "x:coherence-timeline", "v": 2}, {"id": "new"}]}, m)
    assert [l["id"] for l in out["layers"]] == ["a", "x:coherence-timeline", "x:coherence-timeline-t98", "new"]
    assert out["layers"][1]["v"] == 2
