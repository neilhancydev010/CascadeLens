"""Coherence through time for one track (audit P0.5): every catalogued GUNW pair of a track, over one or more frames, as one map layer
with a time step per pair, so the inspector can show a clicked spot's coherence pair by pair.

    python prepare_timeline.py [--view ID] <manifest.json> <track> <frame[,frame...]> <out dir>/data [GUNW .h5 ...]

With several frames (74,75), each pair becomes one time step holding every frame's raster, as Pair A's layers do. A frame
without a given pair is simply absent from that step, and the layer's limitations say so.

--view ID makes a further series beside the main one (another track, such as t98): its layer id, groups and fragment get
the suffix, so the main series is left alone.

The out dir must end in a folder named data (asset paths are written relative to its parent, as in frontend/public).

Each pair goes through the same pipeline as Pair A (inspection, QA gates, the product's own mask, zero-fill and component
rules) and the same fixed 0 to 1 colour range, so steps are drawn alike. Values are stored per pair, never interpolated.
Writes, laid out like frontend/public: sampling/<group>, tiles/<group>, and timeline-<case>.json, a fragment that
merge_observability.py folds into the manifest. Downloads nothing.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import pipeline  # noqa: E402

NAME = re.compile(r"_GUNW_\d{3}_(\d{3})_([AD])_(\d{3})_\d{3}_(\d{4})_\w{2}_(\d{8})T\d{6}_\d{8}T\d{6}_(\d{8})T\d{6}_")


def pair_of(path: pathlib.Path) -> tuple[int, int, str, str, str] | None:
    m = NAME.search(path.name)
    if not m:
        return None
    iso = lambda s: f"{s[:4]}-{s[4:6]}-{s[6:]}"  # noqa: E731
    return int(m.group(1)), int(m.group(3)), m.group(4), iso(m.group(5)), iso(m.group(6))


def main(argv: list[str]) -> None:
    argv = list(argv)
    view = None
    if "--view" in argv:
        i = argv.index("--view")
        view = argv[i + 1]
        del argv[i:i + 2]
    sfx = f"-{view}" if view else ""
    man, track, out = pathlib.Path(argv[0]), int(argv[1]), pathlib.Path(argv[3])
    frames = sorted(int(f) for f in argv[2].split(","))
    files = sorted(pathlib.Path(p) for p in argv[4:])
    m = json.loads(man.read_text(encoding="utf-8"))
    case = m["caseStudy"]["id"]
    cfg = json.loads((ROOT / "processing/configs/pipeline.json").read_text())
    cat = json.loads((ROOT / "data/metadata/catalogue.json").read_text())
    recs = cat if isinstance(cat, list) else next(v for v in cat.values() if isinstance(v, list))
    pairs, granules = {}, []
    for p in files:
        info = pair_of(p)
        if not info or info[0] != track or info[1] not in frames:
            print("skipped (other track or frame):", p.name)
            continue
        _, fr, mode, ref, sec = info
        g = next(r for r in recs if r["file_id"] == p.stem)
        group = f"{case}-coherence{sfx}-{ref.replace('-', '')}"
        state, records = pipeline.process_granule({**g, "group": group}, p, cfg, ROOT / "data/processed/timeline", ROOT / "data/qa")
        if state["status"] == "invalid":
            raise SystemExit(f"{p.name} failed the QA gates: {state.get('reason')}")
        rec = next(r for r in records if r["measurement"] == "gunw-coherence")
        entry = pairs.setdefault((ref, sec), {"group": group, "modes": set(), "recs": [], "frames": []})
        entry["modes"].add(mode)
        entry["recs"].append(rec)
        entry["frames"].append(fr)
        granules.append(p.stem)
        print(f"{ref} to {sec}, frame {fr} (mode {mode}): valid {rec['valid_fraction']:.1%}, masked {rec['masked_fraction']:.1%}")
    steps = []
    for (ref, sec), e in pairs.items():
        if len(e["modes"]) > 1:
            raise SystemExit(f"{ref} to {sec}: frames in different radar modes {sorted(e['modes'])}; they are not one pair")
        # every frame of this pair in one layer fragment, so a step holds one source per frame
        frag = pipeline.finalize_layer("gunw-coherence", e["recs"], cfg, out, ROOT / "data/processed/timeline/prepared")
        days = (__import__("datetime").date.fromisoformat(sec) - __import__("datetime").date.fromisoformat(ref)).days
        steps.append({"label": f"{ref}/{sec}", "days": days, "mode": next(iter(e["modes"])), "sources": frag["sources"], "frames": sorted(e["frames"])})
    if len(steps) < 2:
        raise SystemExit("Need at least two pairs of the same track")
    steps.sort(key=lambda s: s["label"])
    modes = sorted({s["mode"] for s in steps})
    lengths = sorted({s["days"] for s in steps})
    held = sorted({f for s in steps for f in s["frames"]})
    gaps = [f"Frame {f} has no pair for {s['label'].replace('/', ' to ')}." for s in steps for f in held if f not in s["frames"]]
    fr_text = f"frame {held[0]}" if len(held) == 1 else f"frames {' and '.join(map(str, held))}"
    # display settings from the event pair's coherence layer of the same track, so the pass direction is that track's own
    base = next((l for l in m["layers"] if l["measurementType"] == "gunw-coherence" and l.get("groupId") and l.get("track") == track and l.get("status") == "sampleable"),
                next(l for l in m["layers"] if l["id"] == "pair-a:gunw-coherence"))
    if base.get("track") != track:
        raise SystemExit(f"No processed event-pair coherence layer for track {track}; run process_nisar.py for it first")
    layer = {**{k: base[k] for k in ("mission", "instrument", "productType", "orbitDirection", "crs", "attribution", "productMaturity", "postingM", "units", "kind", "stats", "legend")},
             "id": f"{case}:coherence-timeline{sfx}", "groupId": None, "name": f"Coherence through time (Track {track}, {fr_text})",
             "category": "gunw", "measurementClass": "measurement", "measurementType": "gunw-coherence", "track": track, "frames": held,
             "qualityLayerIds": [], "status": "sampleable", "statusReason": None, "sourceGranules": granules,
             "acquisition": {"reference": steps[0]["label"].split("/")[0], "secondary": steps[-1]["label"].split("/")[1]},
             "sources": steps[0]["sources"], "timeSteps": [{"label": s["label"], "sources": s["sources"]} for s in steps],
             "explanation": {"what": f"Coherence of every catalogued Track {track} pair over {fr_text}, one time step per pair, from {steps[0]['label'][:10]} to {steps[-1]['label'][-10:]}.",
                             "measures": "How alike the radar echoes stayed between the two dates of each pair, 0 to 1, on the unwrapped grid, with the product's own mask applied.",
                             "inspect": "Click a spot and open the Inspector: the chart shows that spot in each pair. Play the steps under Simulate, Time replay.",
                             "establishes": "Whether a spot stayed coherent before, across and after the event. It does not say what changed, or measure movement."},
             "limitations": [f"Pairs are not alike: lengths {', '.join(str(d) for d in lengths)} days and radar modes {', '.join(modes)} in the file names. Longer pairs and different modes lower coherence by themselves.",
                             "One value per pair, nothing interpolated between pairs.", *gaps, "Provisional data."]}
    frag = {"case": case, "layers": [layer]}
    out.mkdir(parents=True, exist_ok=True)
    (out / f"timeline-{case}{sfx}.json").write_text(json.dumps(frag, indent=1), encoding="utf-8")
    print(f"{len(steps)} steps -> {out / f'timeline-{case}{sfx}.json'}")


if __name__ == "__main__":
    main(sys.argv[1:])
