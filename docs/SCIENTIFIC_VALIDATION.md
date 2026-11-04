# Scientific validation

## Products inspected

| Group | Product | Track, direction | Frames | Status |
|---|---|---|---|---|
| Pair A, 16→28 Aug 2026 | GUNW | 48 descending | 74, 75 | Downloaded, inspected, QA passed, prepared |
| Pair A | GOFF | 48 descending | 74, 75 | Downloaded, inspected, QA passed, prepared |
| Pair B, 19→31 Aug 2026 | GOFF | 98 ascending | 15, 16 | Downloaded, inspected, QA passed, prepared |
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

### Coherence: clear contrast along the mapped channel

| Frame | Median inside UNOSAT extent | Median nearby |
|---|---|---|
| 74 | 0.19 | 0.46 |
| 75 | 0.16 | 0.52 |

Two independent frames agree, and they agree with independent UNOSAT mapping. Low coherence has other causes, and river channels may be low anyway. **A pre-event control pair over the same channel has not been done, and it would be the proper test.**

### Phase: mostly unusable inside the extent

Only 15% and 19% of phase pixels inside the extent are valid. 40% and 45% are masked, mostly because they could not be reliably unwrapped.

### The source: no data in Pair A, strong signal in Pair B

The detachment zone and barrier lakes are 100% masked in Pair A: they fall in a swath gap. Pair B frame 16 covers them.

| Pair B, frame 16 | Detachment zone | Nearby channel terrain |
|---|---|---|
| Median correlation peak | 0.18 | 0.63 |
| Median SNR | 3.3 | 9.8 |
| Range offsets flagged or masked | 60% | 0.6% |

Image matching largely fails at the source, which is what a heavily changed surface can look like. Steep terrain, layover and snow can also reduce matching. Pair B has no GUNW here yet, so no coherence is available at the source, though the catalogue lists one.

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

### Evidence for GOFF layer 3

On the sample file, layer 3 (window 196 × 128, search 16) has an offset standard deviation of 1.7 m, against 10.7 m and 14.4 m for layers 2 and 1. Its small search window could miss very large shifts.

## LANDMET test

A completely different dataset, run as a test of the product. `tests/processing/test_landmet.py`.

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
| Mask component label 0, for phase only | ATBD 5.9.1.7 |
| Do not mosaic frames | Frames are unwrapped separately, about 50 radians apart |
| Use one release ID | Avoid mixing processing versions |
| Use GCOV mask value 0 only when flagged | Rev E, plus sample behaviour |

## Open questions

**For the NISAR team or ASF (uso@asf.alaska.edu). Not sent:**

> For L2 GUNW `unwrappedPhase`: what is the sign relationship between phase and line-of-sight range change? Is positive phase motion toward or away from the sensor, and is it secondary minus reference? How should the phase be referenced before converting to displacement? Should `ionospherePhaseScreen` be subtracted from `unwrappedPhase`?

The ATBD gives the magnitude, φ = (4π/λ)·δr, and the file gives `centerFrequency`, so λ can be computed. Neither says which direction is positive. A displacement layer stays disabled until this is answered.

**Worth doing next:**

- A pre-event control pair, to test whether the channel is normally low in coherence.
- The Track 98 GUNW for 19→31 August, for coherence at the source.
- Why every granule fails NISAR's `identification` QA check.

**In the reference data:**

- The true date of the UNOSAT detachment zone layer.
- Why the mapped extent (64.91 km²) differs from reported figures of about 30 km².
