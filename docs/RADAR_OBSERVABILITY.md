# Radar Observability, explanations and evidence reports

Added November 2026. These three tools answer, for any spot on the map: *could NISAR judge this place*, *what could explain what it shows*, and *what exactly was measured there*.

## 1. Radar Observability ("Can the radar see it?")

**Question.** For each spot, could a NISAR pair (a) see a surface change between its dates, and (b) measure ground movement? The two tasks are judged separately, because what spoils one does not spoil the other: low coherence *is* the disturbance signal, but it ruins a movement measurement.

**Inputs.** One GUNW pair (the event pair) and, when available, a pre-event baseline GUNW of the same track and frame; optionally the same two pairs for a neighbouring frame (`--also`); the Copernicus DEM GLO-30. Nothing is downloaded by the code.

| Case | Event pair | Baseline pair | Track / frame | Incidence (5th to 95th pct) |
|---|---|---|---|---|
| Rasuwa | 16 to 28 Aug 2026 | 23 Jul to 16 Aug 2026 | 48 descending / 74 | 32.3 to 38.2° |
| Rasuwa | 16 to 28 Aug 2026 | 23 Jul to 16 Aug 2026 | 48 descending / 75 | 32.1 to 38.2° |
| Rasuwa, second view | 19 to 31 Aug 2026 | 26 Jul to 19 Aug 2026 | 98 ascending / 16 | 39.5 to 44.8° |
| Tsho Rolpa | 16 to 28 Aug 2026 | 23 Jul to 16 Aug 2026 | 48 descending / 74 | 43.3 to 43.9° |

For Rasuwa, frame 74 is assessed first. A cell outside frame 74 takes frame 75's flags when frame 75 covers it (`combine_frames`). Of the 5,043,504 cells in the case area, frame 74 assesses 2,485,353 and frame 75 adds 1,584,616. The manifest lists each frame's pair, granules, incidence and sensitivity under `observability.frames`.

**Method, version 2** (`processing/src/cascade_lens/observability.py`, run by `processing/scripts/prepare_observability.py`). The analysis grid is 40 m in UTM zone 45N. Each cell keeps separate reason flags (16-bit), never one blended score:

| Flag | Bit | Rule |
|---|---|---|
| Outside the frame checked | 1 | Outside the product's `boundingPolygon`. A neighbouring frame may cover it; it is not assessed here |
| No data | 2 | Inside the frame, but the product holds no coherence value, or its mask holds the fill value 255 |
| Layover | 4 | Ground slope facing the radar, measured along the horizontal look direction, is steeper than the incidence angle |
| Shadow | 8 | Slope facing away is steeper than 90° minus the incidence angle (active shadow only) |
| Low coherence | 16 | Event-pair coherence below 0.3 |
| No reliably unwrapped phase | 32 | Component label 0 or the component fill value (read from the file), non-finite phase, or phase exactly 0 (the product's fill in unwrapping gaps) |
| Low baseline coherence | 64 | Baseline-pair coherence below 0.3 |
| Flagged by the product's mask | 128 | The event product's own `unwrappedInterferogram/mask` marks water, an invalid subswath or an image anomaly |
| Geometry not assessed | 256 | Elevation, incidence angle or look direction missing or invalid, so layover and shadow cannot be checked |
| Baseline has no valid value | 512 | The baseline product holds no value, or its mask marks fill, water, an invalid subswath or an image anomaly |

**Reading the mask.** In these Provisional (P05023) files the mask is a 32-bit field. The low byte holds three decimal digits: water (hundreds), the reference subswath (tens) and the secondary subswath (units); a subswath of 0 means no valid subswath, and 255 is fill. Bits 8 to 15 and 16 to 23 flag anomalies in the secondary and reference images, and bit 24 marks where the ionosphere screen was interpolated. Bit 24 is set on 37 to 39% of pixels. It is not a quality failure, so it is not treated as one. An earlier decoder read the digits from the whole number; on the event pair that wrongly kept 0.14 to 0.15% of pixels and masked none wrongly. `quality.decode_gunw_mask` now reads the low byte only, and a test checks it on the real layout.

Every flag uses one coherence product: `unwrappedInterferogram/{pol}/coherenceMagnitude`. It shares a grid with the unwrapped phase, the components and the mask, and it is the layer the app shows as "Coherence magnitude". Its 80 m pixels are sampled nearest-neighbour onto the 40 m grid, so each product pixel covers 2 × 2 cells; the finer grid exists for the terrain geometry. A product without its mask is refused.

The look direction and incidence come from the product's own `radarGrid` cubes (`losUnitVectorX/Y`, `incidenceAngle`), at the cube height nearest the median terrain height. NISAR looks left; for frame 74 the unit vector toward the sensor is about 0.55 west and 0.17 north.

**Classes per task.** In order of precedence: outside the frame checked (class 5); no valid data in the product, meaning no value or flagged by the product's mask (class 4); hidden by terrain (class 3); not assessed, when the geometry or, for *disturbance*, the baseline is missing (class 6). Otherwise, for *disturbance*, "seen but not reliable" if the baseline was incoherent; for *movement*, if coherence is low or the phase was not reliably unwrapped (class 2). Everything else is usable (class 1). Disturbance is not assessed at all without a baseline pair. Zone verdicts: 50% usable or more is "enough evidence", 20 to 50% "partial", under 20% "insufficient".

**Sensitivity.** The usable share for movement is recomputed at coherence thresholds of 0.2, 0.3 and 0.4 with the same rule as the movement class, over every cell inside the frame footprint. The threshold is a project choice, so all three are reported, for each frame separately.

**Version 1, withdrawn.** The first version read the wrapped-grid coherence, ignored the product's mask, let a missing elevation or viewing angle count as visible, and accepted the component fill value. In the Rasuwa detachment zone, every frame-74 pixel is flagged by the product's own mask (coherence, phase, components and the GOFF mask alike), yet version 1 reported a surface change as visible on 66% of it. Both cases were rebuilt with version 2 on 13 November 2026, and the app shows only version 2 figures. It still withholds any observability block without `methodVersion` 2.

**Rebuild** (needs the raw GUNW files; nothing is downloaded). Replace the paths with yours, then run the hazards step on the new flags and merge. `--also` adds a neighbouring frame, as an event GUNW and a baseline GUNW (or `-` for none) on the same grid, pairs and track:

```bash
python processing/scripts/prepare_observability.py frontend/public/data/manifests/manifest.json <event GUNW f074 .h5> <baseline GUNW f074 .h5> frontend/public/data/sampling/context/copdem_glo30.tif frontend/public/data/vectors data/interim/observability unosat_detachment_zone.geojson unosat_mudflow_extent.geojson --also <event GUNW f075 .h5> <baseline GUNW f075 .h5>
```

**Results, version 2** (rebuilt 13 November 2026; Rasuwa over frames 74 and 75, Tsho Rolpa over frame 74).

| Zone | Change visible: usable | Movement: usable | No valid data in the product | Outside the frames checked |
|---|---|---|---|---|
| Rasuwa detachment zone (UNOSAT) | 0% | 0% | 100% | 0% |
| Rasuwa mountain source area | 21.9% | 19.5% | 58.2% | 0% |
| Rasuwa mapped mudflow (UNOSAT) | 29.7% | 11.8% | 29.9% | 14.0% |
| Bhote Koshi corridor | 64.0% | 72.5% | 0% | 0% |
| Trishuli corridor | 49.7% | 56.5% | 17.8% | 18.3% |
| Rasuwa, whole case area | 44.0% | 48.1% | 20.4% | 19.3% |
| Tsho Rolpa lake bookmark | 65.0% | 61.7% | 6.9% | 0% |
| Tsho Rolpa lake outline | 4.3% | 5.7% | 90.5% | 0% |
| Tsho Rolpa, whole case area | 55.1% | 44.8% | 1.6% | 0% |

Movement usable at coherence thresholds 0.2, 0.3 and 0.4: 61.2%, 57.1% and 49.3% for Rasuwa frame 74; 63.6%, 60.6% and 53.6% for frame 75; 46.9%, 44.8% and 41.6% for Tsho Rolpa.

**The detachment zone.** The product holds no usable measurement there for either task. Its mask gives every pixel the value 10: reference subswath 1, secondary subswath 0. That means no valid subswath in the 28 August acquisition, a gap in that acquisition's coverage, not water. The unwrapped phase, components and coherence share that mask, so all three are unusable there. Two earlier statements went too far: the story first called the area a swath gap without checking, and the 6 November correction then read the coherence values there without the mask. The swath gap is now confirmed from the mask digits. Pair B (track 98) reaches the source with pixel offsets only.

**The Tsho Rolpa lake.** The mask marks 95% of the product pixels inside the lake outline as water, so the lake outline is almost all "No valid data in the product". The lake bookmark is a wider box that includes the moraine and the valley sides, which is why it scores much higher.

**Version 1 for comparison** (withdrawn, computed without the product's mask, frame 74 only): detachment zone 66% and 0%; mapped mudflow 34% and 9%, 52% outside; Bhote Koshi 70% and 76%; Trishuli 3% and 4%, 95% outside; Tsho Rolpa lake bookmark 70% and 65%. Sensitivity was 95%, 82% and 67%.

### 1b. A second viewing direction: Track 98, ascending

Track 98 passes on the ascending orbit and looks at the slopes from the other side (look vector toward the sensor about 0.65 east and 0.17 north, against 0.55 west for Track 48). Frame 16 covers the whole Rasuwa case area; frame 15 covers 4% of it and is not used. The same method (version 2) runs on its own pairs and writes its own flags, layers and block (`observabilityViews.t98`). The two directions are compared cell by cell on the same 40 m grid and never merged into one reason. The app answers for each direction separately.

```bash
python processing/scripts/prepare_observability.py frontend/public/data/manifests/manifest.json <event GUNW t98 f016 .h5> <baseline GUNW t98 f016 .h5> frontend/public/data/sampling/context/copdem_glo30.tif frontend/public/data/vectors data/interim/obs-t98/data unosat_detachment_zone.geojson unosat_mudflow_extent.geojson --view t98 --compare frontend/public/data/sampling/rasuwa-2026/observability-flags.tif
```

| Zone | Change: Track 98 | Change: either track | Movement: Track 98 | Movement: either track |
|---|---|---|---|---|
| Detachment zone (UNOSAT) | 35.4% | 35.4% | 0% | 0% |
| Mountain source area | 54.8% | 59.3% | 44.2% | 47.7% |
| Mapped mudflow (UNOSAT) | 43.3% | 54.7% | 13.6% | 21.7% |
| Bhote Koshi corridor | 79.3% | 93.8% | 85.2% | 93.9% |
| Trishuli corridor | 66.7% | 77.5% | 77.7% | 84.3% |
| Whole case area | 70.1% | 78.8% | 80.6% | 85.5% |

"Either track" counts a cell once if at least one direction could use it. Movement usable from Track 98 at coherence thresholds 0.2, 0.3 and 0.4: 86.8%, 80.6% and 69.9%.

At the detachment zone, Track 98 holds valid data everywhere, unlike Track 48. A change could be judged on 35% of it. The rest is hidden by layover (28%) or was already incoherent before the event (37%). Movement cannot be measured anywhere there from either side: event-pair coherence is low across the zone (median 0.09), and the phase was not reliably unwrapped. Inside the mapped mudflow, Track 98's mask flags 18% as water (the river).

**Limits.** Passive shadow (cast by a distant ridge) is not modelled. Features smaller than the 40 m grid are smoothed. Coherence also falls for wet snow, vegetation or a long time gap, so "change visible" means a change *could* be seen, not that one happened. The products are Provisional.

## 2. "What could explain this?"

`frontend/src/services/hypotheses.ts`. When a spot is clicked, the app reads the values there and weighs five explanations:

1. The ground surface was disturbed (debris flow, landslide, erosion or new deposits).
2. Ordinary seasonal change (vegetation, snow, ice or wet soil).
3. Open water (shown only near a mapped lake or where coherence is below 0.15).
4. A radar viewing artefact.
5. Nothing changed.

The checks it uses are event-pair coherence (low below 0.3, stable at 0.6 or more), the observability flags, pixel offsets compared with the scene's usual spread (half the 2nd to 98th percentile range, with the match quality at or above the scene median), the slope from the DEM (steep at 25° or more), elevation (4,800 m or more counts as snow and ice ground), whether the spot lies inside an independently mapped area (UNOSAT, REACH), and the case-wide control comparison.

**Two viewing directions.** The clues are gathered once per direction (Track 48 and Track 98), each from its own observability flags, event pair, pixel offsets, pre-event pair and control series. A direction that cannot see the spot (outside its frames, no value, or flagged by its product's mask) adds nothing, and the panel says why. The panel refuses to explain only when no direction can see the spot. Each direction's radar check is counted once and labelled with its track, so two directions that agree count twice. Independent mapping, slope and height are counted or listed once. A coherence drop on a side that terrain hides (layover or shadow) is not counted, because the observability check cannot judge change there; it is listed under what would settle it. Where one side is hidden and the other is not, the side that is not hidden counts against a viewing artefact. With one direction, as for Tsho Rolpa, the wording carries no track label.

Each explanation lists the checks for and against it, the context that is not counted, and what would settle it. Only two kinds of check are counted: a radar value at the clicked spot (coherence, pixel offsets, the baseline flags) and independent mapping of that spot (UNOSAT, REACH). Slope, elevation, area-wide figures such as the control comparison, and the absence of mapping are listed as context, because they describe the place without showing that anything happened there. The label counts checks for minus checks against: two or more is "Fits the checks", one is "Partly fits", otherwise "Little support". Without a valid radar value at the spot, the radar-based explanations say "Cannot judge here". **It is never a probability.** Where the radar did not look, or the product's own mask flags the spot, the panel refuses to explain and says what data is missing.

## 3. Evidence report

`frontend/src/services/report.ts`. The Inspector offers a report for the clicked spot as a printable page (print or save as PDF), CSV, GeoJSON or JSON. It holds the observability answers and reasons, the ranked explanations, every sampleable layer's value with its evidence class, observation dates and source file, and the caveats. It is built in the browser from data already shipped with the app; nothing is sent anywhere.

## Evidence classes

Every layer, panel and report carries one class (`frontend/src/services/evidence.ts`): Observed, Derived, Forecast, Hypothesis, Reference, Scenario, Unknown. Missing data is labelled Unknown, never treated as safe.

## 4. Hazard screens (experimental)

`processing/src/cascade_lens/hazard.py`, run by `processing/scripts/prepare_hazards.py` on the same 40 m grid.

**Landslide-prone terrain (Model A, terrain only).** Slope bands (15, 25, 35°), converging hollows (negative plan curvature) and a topographic wetness index (D8 flow accumulation) give Low, Moderate, High or Very high. Each pixel keeps its factor bits for the inspector. A one-event consistency check, not a validation: 56% of the UNOSAT 2026 detachment zone screens High or Very high, against 32% of the whole area (AUC 0.66). The AUC treats every unmapped pixel as a confirmed negative and counts neighbouring pixels as independent, so it shows only that the screen is not inconsistent with this one event. Pixels with no valid elevation are left out. The mudflow runout screens mostly Low (58%), as expected for valley floors where debris settles. No geology, soil, land cover or rainfall, and no calibration: it is a screen, not a susceptibility model or forecast.

**Road exposure.** Trunk, primary, secondary and tertiary OpenStreetMap roads cut into 250 m stretches. High: crosses the 2026 mapped mudflow or UNOSAT affected roads, or 30% of the ground within 150 m screens High or Very high. Moderate: 10% or more, or within 100 m of a mapped river (OpenStreetMap). Being near a river is a reason to look, not evidence of bank erosion or flooding. Ground with no valid elevation is left out of the steep share. Each stretch also says whether the event pair could watch it (share of its corridor usable for change), and, with `--other-view t98`, the share usable from Track 98 and from either direction. The Track 48 rating is never replaced by the other view. Of 153.4 km screened, 73.3 km rate High. Track 48 could not watch 28.2 km (13.1 km of them High); counting either direction, 4.8 km (2.7 km High). Before frame 75 was assessed, 109 km lay beyond the frame checked.

**Model B (rainfall triggering)** is blocked by data: it needs GPM IMERG rainfall, soil moisture and a Nepal-calibrated threshold.
