# Scientific validation

## Products inspected

| Group | Product | Track, direction | Frames | Status |
|---|---|---|---|---|
| Pair A, 16→28 Aug 2026 | GUNW | 48 descending | 74, 75 | Downloaded, inspected, QA passed, prepared |
| Pair A | GOFF | 48 descending | 74, 75 | Downloaded, inspected, QA passed, prepared |
| Pair B, 19→31 Aug 2026 | GUNW | 98 ascending | 16 | Downloaded, inspected, QA passed, prepared (13 Nov). Frame 15 covers 4% of the case area and is not used |
| Pair B | GOFF | 98 ascending | 15, 16 | Downloaded, inspected, QA passed, prepared |
| Track 98 series, 26 Jul → 6 Oct 2026 | GUNW | 98 ascending | 16 | Four more pairs (one before the event, three after), QA passed, coherence prepared |
| Track 48 series, 23 Jul → 3 Oct 2026 | GUNW | 48 descending | 74, 75 | Four more pairs in each frame, QA passed, coherence prepared |
| Snapshots, 28 and 31 Aug | GCOV | 48 and 98 | 74, 75, 15, 16 | Catalogued only. 31 GB needed |

All granules are PROVISIONAL, CRID P05023. `tests/integration/test_rasuwa_data.py` checks them.

## Metadata checks, from the real files

| Check | Result |
|---|---|
| Track, frame, direction, dates match the catalogue and the brief | Yes, all six granules |
| Reference before the event, secondary after it | Yes |
| Product maturity, from the file's DOI | Provisional (P05023) |
| Required datasets present, documented units match | Yes |
| Stored rasters equal the source arrays | Yes, exact |
| NISAR's own QA | All checks pass except `identification`. The public samples fail that check too. Its reason has not been established |

## Results for the event

**Descriptive evidence, not proof of cause.** Reproduce with `python processing/scripts/analyse_pair.py pair-a` and `pair-b`. Results are in `data/qa/`. "Nearby" means within 1 km of the UNOSAT extent, outside it.

**Rebuilt on 13 November 2026** from the raw files, with the P0.1 corrections and the 32-bit mask fix below. All six original granules matched their recorded SHA-256. The coherence medians did not move. Whole-frame valid phase fell by 0.11 percentage points in each frame, where zero-filled phase is now masked.

### Coherence: clear contrast along the mapped channel

| Frame | Median inside UNOSAT extent | Median nearby |
|---|---|---|
| 74 | 0.19 | 0.46 |
| 75 | 0.16 | 0.52 |
| Track 98, frame 16 (Pair B) | 0.13 | 0.46 |

Valid shares inside the extent: 36.5% (frame 74), 44.0% (frame 75) and 81.2% (Track 98). In Track 98 the rest is masked as water (the river).

Two frames and two viewing directions agree, and they agree with independent UNOSAT mapping. Low coherence has other causes, and river channels may be low anyway.

### Before and after, against ground nearby

Track 48, frame 74. "Inside" is the UNOSAT mudflow extent. "Control" is ground 300 to 1,500 m outside it. Each value is a median of the unwrapped-grid coherence with the product's mask applied, with a 95% interval from a spatial block bootstrap (1 km blocks, 1,000 resamples). Reproduce with `python processing/scripts/prepare_control_series.py`.

| Pair | Days | Mode in file name | Inside | Control | Valid inside |
|---|---|---|---|---|---|
| 23 Jul → 16 Aug (before) | 24 | 4000 | 0.38 (0.35–0.40) | 0.40 (0.39–0.41) | 55% |
| 16 → 28 Aug (across the event) | 12 | 2000 | 0.19 (0.17–0.22) | 0.50 (0.49–0.51) | 37% |
| 28 Aug → 9 Sep | 12 | 2000 | 0.32 (0.30–0.34) | 0.55 (0.53–0.56) | 40% |
| 9 → 21 Sep | 12 | 2000 | 0.43 (0.41–0.46) | 0.55 (0.53–0.56) | 42% |
| 21 Sep → 3 Oct | 12 | 2000 | 0.46 (0.44–0.47) | 0.54 (0.52–0.55) | 38% |

The gap opens only inside the mapped area, then narrows. A seasonal change would be expected to lower both areas, so the pattern is **consistent with surface change in the mapped area. It does not establish the cause.** The comparison is indicative, not like for like: the pair before spans twice as many days and was acquired in a different radar mode, and either difference changes coherence by itself.

**Frame 75, the lower mudflow.** The same method on the frame 75 pairs, a cross-check that is documented here and not shown in the app. Only the part of the mapped mudflow inside frame 75 counts; 36 to 39% of it is valid in each pair. Reproduce with `prepare_control_series.py` on the five frame 75 files.

| Pair | Days | Mode in file name | Inside | Control |
|---|---|---|---|---|
| 23 Jul → 16 Aug (before) | 24 | 4000 | 0.28 (0.26–0.29) | 0.42 (0.41–0.43) |
| 16 → 28 Aug (across the event) | 12 | 2000 | 0.16 (0.15–0.18) | 0.54 (0.53–0.55) |
| 28 Aug → 9 Sep | 12 | 2000 | 0.26 (0.24–0.28) | 0.59 (0.58–0.60) |
| 9 → 21 Sep | 12 | 2000 | 0.38 (0.35–0.39) | 0.59 (0.58–0.60) |
| 21 Sep → 3 Oct | 12 | 2000 | 0.41 (0.38–0.43) | 0.62 (0.61–0.63) |

The pattern matches frame 74: the gap opens across the event (0.14 before, 0.37 across), then narrows. Unlike frame 74, the lower mudflow was already clearly less coherent than the ground around it before the event, so less of the across-event gap is new.

**From the opposite side.** Track 98, frame 16, the same zone and method. Every Track 98 pair was acquired in the same radar mode (4000), so mode cannot explain the difference here; the pair before is still twice as long. Valid inside is 77% in every pair: only the river is masked, and the water mask is the same in all five.

| Pair | Days | Mode in file name | Inside | Control |
|---|---|---|---|---|
| 26 Jul → 19 Aug (before) | 24 | 4000 | 0.31 (0.28–0.33) | 0.40 (0.39–0.40) |
| 19 → 31 Aug (across the event) | 12 | 4000 | 0.13 (0.12–0.14) | 0.49 (0.48–0.50) |
| 31 Aug → 12 Sep | 12 | 4000 | 0.27 (0.25–0.29) | 0.50 (0.49–0.51) |
| 12 → 24 Sep | 12 | 4000 | 0.37 (0.34–0.40) | 0.43 (0.42–0.45) |
| 24 Sep → 6 Oct | 12 | 4000 | 0.29 (0.26–0.31) | 0.31 (0.30–0.32) |

From this side the mapped area was already a little lower before the event (the intervals do not overlap), and the gap widens from 0.09 to 0.36 across it, then narrows. Both directions show the same pattern, with different modes and geometry. Coherence on the control ground also falls in the last two pairs, to 0.43 and then 0.31, so something affected both areas by late September and October. That is a reminder that the control ground changes too.

These figures replace medians from an earlier script that was never in the repository (0.41 and 0.42 before, 0.28 and 0.52 across the event). That script did not apply the mask, and its intervals treated neighbouring pixels as independent. The across-event median inside now matches the pair analysis above (0.19).

### Phase: mostly unusable inside the extent

Only 15.2% and 19.0% of phase pixels inside the extent are valid. 40.5% and 45.3% are masked, mostly because they could not be reliably unwrapped.

### The source: nothing usable in Pair A, very low coherence in Pair B

Pair A's own mask flags every frame-74 pixel of the detachment zone (307 product pixels), and no valid coherence, phase or GOFF value exists anywhere in it. The raw mask settles why. Every one of those pixels has the value 10: water flag 0, reference subswath 1, secondary subswath 0. So the 28 August acquisition has no valid subswath over the source: it is a gap in that acquisition's coverage, not water. The same holds for the barrier lakes. An earlier version of these documents called it a swath gap without checking, which turns out to be right in substance. A later one said a change was visible on 66% of it, from an observability check that ignored the mask, which was wrong. Pair B frame 16 covers the source.

| Pair B, frame 16 | Detachment zone | Nearby channel terrain |
|---|---|---|
| Median coherence (GUNW, valid share) | 0.09 (100%) | 0.46 (99.9%) |
| Median correlation peak | 0.18 | 0.63 |
| Median SNR | 3.3 | 9.8 |
| Range offsets flagged or masked | 60% | 0.6% |

Coherence is very low and image matching largely fails at the source, which is what a heavily changed surface can look like. Steep terrain, layover and snow can also reduce both. From this side, 28% of the zone is hidden by layover, and 37% was already incoherent in the pair before the event. Pair B's mask flags none of the zone, but its phase there was not reliably unwrapped (component 0 everywhere), so it gives no movement value.

### Pixel offsets: no large coherent shift detected

| Pair, component | Inside extent, typical size | Nearby |
|---|---|---|
| A, slant range, frames 74 / 75 | 0.17 / 0.17 m | 0.13 / 0.13 m |
| B frame 16, slant range | 0.05 m | 0.04 m |
| B frame 16, along track | 0.08 m | 0.07 m |

Typical size means the median distance from the scene median. The differences are small, and they are not evidence of a measured movement.

### Ionosphere: the broad stripes are mostly atmospheric

| Frame | Correlation, phase with screen | Phase scatter | After subtracting | After adding |
|---|---|---|---|---|
| 74 | 0.84 | 8.87 rad | 4.79 rad | 15.5 rad |
| 75 | 0.95 | 6.41 rad | 1.98 rad | 12.56 rad |
| Track 98, frame 16 | 0.82 | 1.74 rad | 1.06 rad | 2.70 rad |

This supports the derived ionosphere-removed layer. It also shows why raw phase should never be read as ground motion here.

### Observed but unexplained

A diagonal phase break crosses frame 75. A warm-toned phase feature remains in the west of the area after ionosphere removal. Neither is interpreted here.

## Real-format validation

NASA's [public samples](https://science.nasa.gov/mission/nisar/sample-data/) (2008 scene over California, CRID D00404) tested the software before the Rasuwa files were available. They are not event data. Run `python processing/scripts/fetch_samples.py`, then `tests/integration/test_real_format.py`.

### Bugs found by real files

| Finding | Effect if missed | Fix |
|---|---|---|
| `correlationSurfacePeak` units are `1`, not `unitless` as in spec R3.4 | Every real GOFF rejected | Treat as synonyms |
| GOFF mask exists | Water and invalid pixels shown as valid | Mask applied |
| ATBD 5.9.1.7: label 0 "could not be reliably unwrapped" | Unreliable phase shown as valid | Masked, for phase only |
| GCOV mask is 0 everywhere when masking was not applied | A whole scene masked | Used only when the flag is True |
| Maturity hardcoded | Beta mislabelled | Read from the DOI |
| GDAL rewrote class 0 to 1 while warping validity rasters | Swath gaps drawn as valid on the map | Validity warped with nodata 255 |
| Frames sit about 50 radians apart | A shared colour scale washed out both | Colours relative to each frame's median |

### Errors found in review, 12 November (P0.1)

These were found in our own code, not in the files. The code is fixed and every output was rebuilt with it on 13 November.

| Finding | Effect | Fix |
|---|---|---|
| Observability ignored `unwrappedInterferogram/mask` | Ground the product flags was counted as visible: 66% of the detachment zone | The mask is applied, with its own reason flag. A product without a mask is refused |
| A missing elevation, incidence or look direction counted as usable | Spots that were never checked looked fine | "Geometry not assessed" flag and a "Not assessed" class |
| Component fill counted as a label, and the component map had no no-data class | Fill could pass as unwrapped phase | Fill read from `_FillValue`; no data where the product holds no phase |
| Unwrapped phase stored as exactly 0 counted as valid | 1,201 (frame 74) and 1,217 (frame 75) fill pixels treated as measurements | Exact zero is masked, value kept; no data always wins over masked |
| Observability mixed two coherence products | Flags and the map layer could disagree | Every flag uses the unwrapped-grid coherence shown in the app |
| Sensitivity percentages ignored the unwrapping rule | Usable shares at 0.2, 0.3 and 0.4 were too high | Computed with the movement-class rule |
| Tsho Rolpa movement bounds shown in the app | A dam movement limit in centimetres and a glacier limit extrapolated to "6 m a year", from 12-day pairs | Research output only; no yearly extrapolation |
| "Best supported" could be reached without a radar value at the spot | Slope, height and area-wide figures could rank an explanation | Only radar values at the spot and independent mapping count |
| The mask's digits were read from the whole 32-bit number (found at the rebuild, 13 Nov) | P05023 masks carry anomaly flags in bits 8–23 and an interpolated-ionosphere flag in bit 24 (set on 37–39% of pixels). Read from the whole number, a set bit 24 turned valid subswaths invalid and hid water | Digits read from the low byte; anomaly flags mask the pixel; the ionosphere flag is recorded. About 0.1 percentage point of frame 75 changed; no headline figure moved |

### Evidence for GOFF layer 3

On the sample file, layer 3 (window 196 × 128, search 16) has an offset standard deviation of 1.7 m, against 10.7 m and 14.4 m for layers 2 and 1. Its small search window could miss very large shifts.

## LANDMET test (retired from the app)

A completely different dataset, once run as a test of the product. The case was taken out of the app on 6 November 2026. The pipeline tests remain in `tests/processing/test_landmet.py` and run when the LANDMET file is present. The results below are from 1 November.

| Check | Result |
|---|---|
| Every 1° pixel falls inside its own equal-area cell | Yes |
| Stored values equal the source cells | Yes |
| Physics: skin temperature should peak around local afternoon | 12.9 h local solar time, over low-latitude land |
| Peak moves with longitude | Australia 03 UTC, Nepal 06 UTC, Sahara 12 UTC |
| Variables that are entirely fill | Shown as unavailable, with the reason |
| Implausible values, such as 118.6 m/s wind | Flagged as masked, unchanged |

## Other validation evidence

| Claim | Evidence |
|---|---|
| The browser inspector reads the stored value | Matches rasterio and the source file, in Edge |
| Coordinate transforms are correct | proj4 matches pyproj at a test point |
| Tiles land on the right ground location | Automated mercator round-trip test |
| Masked pixels keep their value | Automated and browser tests |
| Missing data never becomes a number | Tests for NaN, fill, masked, outside and failed cases |
| Processing is deterministic | Identical hashes across two runs |
| Releases are never mixed | Test with real duplicate granule naming |
| A failed gate leaves no outputs | Automated test |
| Other missions stay labelled | Test on the shipped manifest |
| Colour-only products cannot be sampled | Manifest and browser tests |
| No displacement layer exists | Test on the shipped manifest |

## Processing decisions

| Decision | Reason |
|---|---|
| No LOS conversion | Sign convention undocumented |
| Ionosphere-removed phase is a separate derived layer | Raw phase stays available and unchanged |
| Subtract the screen | ATBD writes phase as a sum including the ionosphere, and scatter falls only when subtracting |
| No coherence or SNR threshold | Not needed for display. Raw context is shown instead |
| Mask component label 0 and exact-zero values, for phase only | ATBD 5.9.1.7; the product writes 0 where unwrapping failed |
| Observability honours the product's own mask | The product knows where its values are invalid; ignoring that over-claimed coverage |
| Do not mosaic frames | Frames are unwrapped separately, about 50 radians apart |
| Use one release ID | Avoid mixing processing versions |
| Use GCOV mask value 0 only when flagged | Rev E, plus sample behaviour |

## Open questions

**For the NISAR team or ASF (uso@asf.alaska.edu). Not sent:**

> For L2 GUNW `unwrappedPhase`: what is the sign relationship between phase and line-of-sight range change? Is positive phase motion toward or away from the sensor, and is it secondary minus reference? How should the phase be referenced before converting to displacement? Should `ionospherePhaseScreen` be subtracted from `unwrappedPhase`?

The ATBD gives the magnitude, φ = (4π/λ)·δr, and the file gives `centerFrequency`, so λ can be computed. Neither says which direction is positive. A displacement layer stays disabled until this is answered.

**Worth doing next:**

- A like-for-like pre-event control pair, with the same length and radar mode as the event pair, if the catalogue holds one.
- Why every granule fails NISAR's `identification` QA check.

**In the reference data:**

- The true date of the UNOSAT detachment zone layer.
- Why the mapped extent (64.91 km²) differs from reported figures of about 30 km².
