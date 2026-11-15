# Rasuwa: candidate "cliff impact" sites (Hypothesis)

Source of the idea: a mentor, oral communication, no location or figures given. The mentor said the water hit a cliff edge and "ricocheted at double the force and the other way". CascadeLens tests where it could have happened. It does not confirm that it did.

Built by `processing/scripts/find_impact_sites.py` from data already in the repository: the Simulate flow path, the Copernicus GLO-30 clip (30 m, from before the event), the UNOSAT mudflow extent (preliminary, not field validated), OSM rivers, Pair B (Track 98) coherence and the REACH Sentinel-1 change screening. Every measured input is in `rasuwa-2026-impact-sites.csv`. The method and the physics are in [docs/SCENARIO_WORKING.md](../../docs/SCENARIO_WORKING.md).

## Result

27 bends of at least 45 degrees within 1.5 km have an outer bank of at least 35 degrees within 300 m. Outcomes, by the fixed rules: **12** where the data support a hard outer-bank impact, **14** where the data do not show it, **1** where the data cannot judge.

A control matters more than any single site. On 318 straight cross-sections the mapped extent's edge is 8.8 m higher on the flow's left than on its right (middle half -3.1 to 20.5 m). Before that control, almost every right-hand bend looked like support and almost every left-hand bend did not, which is what a one-sided offset would do. The control is taken off each bend. Even after it, the straight stretches scatter by about 24 m between their quartiles, so a bend's difference of 5 to 20 m is weak evidence on its own. **No site shows the marks clearly enough to point to one place.** The strongest are listed first below.

The expected bends: near km 6 the path turns only 37 degrees over 1.5 km and lies about 5 km from any mapped river (it is a straight line joining the detachment zone and barrier lakes), so it is not a candidate. At km 13 (S1) the path turns 55 degrees against a 60 degree wall, but the extent reaches about 105 m *higher on the inner bank*: the opposite of superelevation, so the data do not show an outer-bank impact there.

The run-up bounds (v ≥ √(2g·h_up)) come out at roughly 10 to 30 m/s, even more than 100 km downstream. That is implausibly fast for a flood so far from its source, which says the extent's edge on the valley walls is not a run-up line: a preliminary outline drawn generously onto the slopes, and a 30 m terrain model, both lift it. Treat those numbers as what the formula gives from these inputs, not as speeds.

The radar columns are descriptive only. Low coherence on one bank can come from steep slopes, layover, vegetation or water as well as from damage, and the REACH screening only covers areas around buildings mapped before the event. They do not enter the outcome.

| Site | km | Turn | Outer bank | Wall slope | R_c (m) | b (m) | Δh raw (m) | Control (m) | Δh (m) | h_up outer (m) | v, superelevation k 5 to 1 (m/s) | v ≥, run-up (m/s) | Coherence outer / inner | Outcome |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S16 | 138.01 | -89.0° | left | 43.7° | 530.9 | 105.7 | 30.4 | 8.8 | 21.6 | 34.1 | 14.6 to 32.6 | 25.9 | 0.312 / 0.149 | supports a hard outer-bank impact |
| S15 | 135.02 | -51.1° | left | 39.5° | 866.1 | 146.1 | 29.4 | 8.8 | 20.6 | 29.5 | 15.5 to 34.6 | 24.1 | 0.244 / 0.329 | supports a hard outer-bank impact |
| S2 | 66.01 | -64.8° | left | 51.6° | 698.0 | 533.7 | 27.4 | 8.8 | 18.6 | 49.1 | 6.9 to 15.4 | 31.0 | 0.111 / 0.059 | supports a hard outer-bank impact |
| S3 | 74.02 | -49.5° | left | 40.3° | 891.6 | 290.9 | 26.4 | 8.8 | 17.6 | 53.2 | 10.3 to 23.0 | 32.3 | 0.33 / 0.209 | supports a hard outer-bank impact |
| S23 | 173.01 | -66.8° | left | 37.8° | 679.9 | 111.2 | 21.5 | 8.8 | 12.7 | 25.2 | 12.3 to 27.6 | 22.2 | 0.313 / 0.253 | supports a hard outer-bank impact |
| S21 | 167.99 | -46.9° | left | 48.7° | 938.6 | 120.0 | 20.8 | 8.8 | 12.0 | 24.4 | 13.6 to 30.3 | 21.9 | 0.384 / 0.248 | supports a hard outer-bank impact |
| S4 | 75.94 | 64.2° | right | 50.8° | 691.5 | 240.0 | 0.0 | -8.8 | 8.8 | 20.0 | 7.1 to 15.8 | 19.8 | 0.163 / 0.183 | supports a hard outer-bank impact |
| S19 | 163.01 | -48.5° | left | 45.7° | 911.5 | 92.2 | 17.6 | 8.8 | 8.8 | 25.1 | 13.1 to 29.2 | 22.2 | 0.202 / 0.146 | supports a hard outer-bank impact |
| S18 | 155.99 | 88.7° | right | 53.6° | 532.8 | 287.8 | -0.6 | -8.8 | 8.2 | 10.7 | 5.5 to 12.2 | 14.5 | 0.097 / 0.121 | supports a hard outer-bank impact |
| S27 | 194.0 | 70.4° | right | 39.5° | 650.1 | 197.0 | -0.6 | -8.8 | 8.2 | 6.1 | 7.3 to 16.3 | 10.9 | 0.435 / 0.106 | supports a hard outer-bank impact |
| S8 | 98.99 | -64.0° | left | 43.2° | 705.6 | 199.7 | 16.2 | 8.8 | 7.4 | 20.8 | 7.2 to 16.0 | 20.2 | 0.455 / 0.249 | supports a hard outer-bank impact |
| S7 | 88.98 | 79.3° | right | 41.6° | 582.5 | 393.4 | -1.5 | -8.8 | 7.3 | 12.6 | 4.6 to 10.3 | 15.7 | 0.238 / 0.091 | supports a hard outer-bank impact |
| S6 | 84.02 | -57.2° | left | 36.2° | 777.8 | 167.6 | 12.8 | 8.8 | 4.0 | 27.2 | 6.0 to 13.5 | 23.1 | 0.335 / 0.25 | does not show it |
| S12 | 123.99 | 87.1° | right | 48.5° | 540.1 | 119.9 | -4.9 | -8.8 | 3.9 | 3.5 | 5.9 to 13.1 | 8.3 | 0.253 / 0.308 | does not show it |
| S20 | 164.99 | 72.1° | right | 59.7° | 635.8 | 154.0 | -5.9 | -8.8 | 2.9 | 10.8 | 4.8 to 10.8 | 14.6 | 0.324 / 0.311 | does not show it |
| S11 | 120.99 | -64.0° | left | 41.9° | 705.9 | 150.8 | 10.5 | 8.8 | 1.7 | 16.5 | 4.0 to 8.8 | 18.0 | 0.375 / 0.393 | does not show it |
| S9 | 106.01 | 60.0° | right | 41.0° | 747.6 | 152.1 | -7.9 | -8.8 | 0.9 | 5.5 | 2.9 to 6.6 | 10.4 | 0.338 / 0.472 | does not show it |
| S24 | 179.01 | -61.1° | left | 38.4° | 716.6 | 149.2 | 9.7 | 8.8 | 0.9 | 17.4 | 2.9 to 6.5 | 18.5 | 0.353 / 0.306 | does not show it |
| S26 | 191.98 | -104.3° | left | 43.8° | 467.5 | 303.2 | 9.4 | 8.8 | 0.6 | 17.2 | 1.3 to 3.0 | 18.4 | 0.344 / 0.14 | does not show it |
| S22 | 171.01 | 65.2° | right | 54.4° | 694.4 | 110.7 | -10.2 | -8.8 | -1.4 | 4.0 | not given | 8.9 | 0.441 / 0.181 | does not show it |
| S10 | 111.01 | -60.8° | left | 46.6° | 739.3 | 179.1 | 5.6 | 8.8 | -3.2 | 14.7 | not given | 17.0 | 0.43 / 0.286 | does not show it |
| S5 | 79.0 | -54.7° | left | 37.7° | 815.7 | 309.3 | 4.0 | 8.8 | -4.8 | 28.9 | not given | 23.8 | 0.233 / 0.102 | does not show it |
| S17 | 152.02 | 87.9° | right | 52.5° | 528.1 | 219.8 | -14.2 | -8.8 | -5.4 | 17.6 | not given | 18.6 | 0.178 / 0.349 | does not show it |
| S14 | 133.01 | 87.8° | right | 42.8° | 538.8 | 148.2 | -15.4 | -8.8 | -6.6 | 6.6 | not given | not given | 0.141 / 0.416 | cannot judge |
| S13 | 126.0 | -115.3° | left | 46.8° | 442.6 | 163.7 | 1.6 | 8.8 | -7.2 | 5.4 | not given | 10.3 | 0.3 / 0.262 | does not show it |
| S25 | 180.98 | 49.9° | right | 51.6° | 885.5 | 239.8 | -16.3 | -8.8 | -7.5 | 10.4 | not given | 14.3 | 0.451 / 0.298 | does not show it |
| S1 | 12.98 | 54.6° | right | 59.7° | 812.6 | 530.9 | -113.5 | -8.8 | -104.7 | 171.3 | not given | 58.0 | 0.131 / 0.13 | does not show it |

Speeds are what the formulas give from these inputs, not measurements. Where a bend cannot be judged, no speed is given.
Turn: positive is to the left. Outer bank: the side the flow would hit going straight on.

## What to ask the mentor

1. Where: the village, bridge, river bend or km along the Bhote Koshi or Trishuli.
2. The source: a report (which), a video or photo (where it can be seen), or a field visit (who, when).
3. What "double" was compared with: the push on the rock (which physics allows, up to twice that of a flow that simply stops), the damage seen, or how fast or far the water went (which physics does not allow: water leaving a wall carries less energy than it arrived with).
4. When in the event, and whether it was the water, the mud and boulders, or a landslide into the river.
