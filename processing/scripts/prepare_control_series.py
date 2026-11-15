"""Coherence inside a mapped zone against control ground, across GUNW pairs of one track and frame (the "before/after" chart).

    python prepare_control_series.py [--view ID] <manifest.json> <zone.geojson> <out dir> <gunw.h5> [<gunw.h5> ...]

--view ID writes the series for another viewing direction (such as t98) under controlSeriesViews[ID], beside the main one.

Example for Rasuwa, frame 74 (use every pair you hold, before and after the event):
    python processing/scripts/prepare_control_series.py frontend/public/data/manifests/manifest.json \\
        frontend/public/data/vectors/unosat_mudflow_extent.geojson data/interim/observability \\
        data/raw/nisar/NISAR_L2_PR_GUNW_*_048_D_074_*.h5

Writes <out dir>/control-<case>.json, which merge_observability.py folds into the manifest as `controlSeries`.
Reads the files only; downloads nothing. Method: cascade_lens.coherence_series.
"""
from __future__ import annotations

import json
import pathlib
import sys

from shapely.geometry import shape
from shapely.ops import unary_union

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from cascade_lens import coherence_series as cs  # noqa: E402

ZONE_NAMES = {"unosat_mudflow_extent": "UNOSAT mudflow extent"}


def main(argv: list[str]) -> None:
    argv = list(argv)
    view = None
    if "--view" in argv:
        i = argv.index("--view")
        view = argv[i + 1]
        del argv[i:i + 2]
    if len(argv) < 4:
        sys.exit(__doc__)
    man, zone_file, out = (pathlib.Path(a) for a in argv[:3])
    files = [pathlib.Path(a) for a in argv[3:]]
    m = json.loads(man.read_text(encoding="utf-8"))
    fc = json.loads(zone_file.read_text(encoding="utf-8"))
    zone = unary_union([shape(f["geometry"]) for f in fc["features"]])
    name = ZONE_NAMES.get(zone_file.stem, zone_file.stem)
    result = cs.series(files, zone, name, m["caseStudy"]["eventDate"])
    out.mkdir(parents=True, exist_ok=True)
    case = m["caseStudy"]["id"]
    path = out / f"control-{case}{f'-{view}' if view else ''}.json"
    if view:
        result["label"] = f"Track {result['track']}, {str(result['direction']).lower()}"
    block = {"controlSeriesViews": {view: result}} if view else {"controlSeries": result}
    path.write_text(json.dumps({"case": case, "layers": [], **block}, indent=1), encoding="utf-8")
    for p in result["pairs"]:
        print(f"{p['pair'][0]} to {p['pair'][1]} ({p['days']} d, mode {p['mode']}): inside {p['inside']} {p['insideCi95']}, outside {p['outside']} {p['outsideCi95']}, valid {p['validPct']}%")
    print("wrote", path)


if __name__ == "__main__":
    main(sys.argv[1:])
