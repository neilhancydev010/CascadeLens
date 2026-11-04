# Methodology

Everything below has been run on the **real Rasuwa granules**, and on NASA's public sample files. It follows the specifications and ATBD, and `inspect` compares them with each real file.

## Pipeline

1. Inspect the HDF5 file. Compare product type, track, frame, direction and dates with the catalogue record.
2. Check that the expected datasets exist and their units match.
3. Clip to the study area on the native grid, without resampling.
4. Classify each pixel in a validity raster.
5. Check the valid-pixel fraction.
6. Write a native-grid COG for sampling and display tiles.
7. Regenerate the manifest. Any failed gate leaves no outputs.

## GUNW phase interpretation

`/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/{pol}/unwrappedPhase` is Float32 in radians, with NaN as fill. It is stored unchanged. Only the tiles apply a colour scale.

The estimated ionospheric phase screen is in the product but is not applied to it. It is available as its own layer. Frames 74 and 75 are unwrapped separately and sit about 50 radians apart, so they are kept as separate sources and never mosaicked.

Phase-like layers are coloured relative to each frame's median, so both frames stay readable. This affects colours only: the inspector shows the stored value.

## Ionosphere-removed phase

`gunw-phase-iono` is a derived layer, not a NISAR product: `unwrappedPhase` minus `ionospherePhaseScreen`. The ATBD writes phase as a sum that includes an ionosphere term. On Pair A, subtraction cut scatter from 8.87 to 4.79 and from 6.41 to 1.98 radians, while addition raised it. The source layers are not changed. Pixels masked in either input are masked here.

## Coherence

`.../{pol}/coherenceMagnitude` at 80 m shares the phase grid, so no resampling is needed. The pipeline refuses to continue if the grids differ. No coherence threshold is applied: `coherence_threshold` stays `null` until the real distribution has been examined.

## Connected components

`.../{pol}/connectedComponents` is UInt16 with fill 65535. Labels are shown as categories. ATBD section 5.9.1.7 says label 0 marks phase that could not be reliably unwrapped, so those phase pixels are masked. Coherence is not affected by this rule.

## Mask

`unwrappedInterferogram/mask` and `pixelOffsets/mask` have three digits: water flag, reference subswath, secondary subswath. A 0 subswath digit means invalid; 255 is fill.

| Validity class | Meaning | Displayed | Value kept |
|---|---|---|---|
| 0 No data | Non-finite, or fill in mask or components | No | n/a |
| 1 Valid | Passed every rule | Yes | Yes |
| 2 Masked | Water, invalid subswath, component label 0 (phase), or flagged outlier | Optional overlay | Yes |

## GOFF offsets

`/science/LSAR/GOFF/grids/frequencyA/pixelOffsets/{pol}/layer{n}/` holds `slantRangeOffset` and `alongTrackOffset` in metres, plus `snr` and `correlationSurfacePeak`. They are raw and unfiltered.

Layer 3 is the default. It has the largest correlation window, and on the sample file its offsets are far cleaner than layers 1 and 2 ([evidence](SCIENTIFIC_VALIDATION.md#evidence-for-goff-layer-3)). Its search window is the smallest, so a very large shift could be missed. Confirm this on the real pair. Set it with `goff_layer`.

Gross outliers are pixels where `|x - median| > k × 1.4826 × MAD`, with `k = 10`. They are flagged, never deleted. The test is global, so large real signals survive unless `k` is set too low. Real data may still need review, because landslide motion is an outlier by nature.

No SNR threshold is applied (`snr_min` is `null`). No offset magnitude is computed.

## GCOV backscatter

The first co-polar term in `listOfCovarianceTerms` is used, for example `HHHH`. It is linear gamma-0 with units of 1. The COG keeps linear values. Tiles use `10·log10(value)`, with nonpositive input having no dB value. The inspector reports both.

Rev E says mask value 255 is outside the acquisition and 0 is partially focused. Value 0 is applied only when `validSamplesSubSwathMaskingApplied` is True: the public samples report False and hold 0 on every pixel. The two dates are separate snapshots and are never differenced.

The known polarimetric phase correction applies to off-diagonal terms and does not affect `HHHH`.

## Coordinate transformations

Each file's EPSG code is read from its `projection` dataset. Pixel-edge transforms are derived from pixel-centre coordinates. Non-uniform grids are refused. The study area is transformed into the file's CRS with densified edges before clipping.

In the browser, proj4 transforms a clicked point into the raster's CRS. UTM results match pyproj to better than a millimetre in the test point. Other projected CRSs are refused, not guessed.

## Raster preprocessing

| Output | Grid | Resampling | Purpose |
|---|---|---|---|
| GeoTIFF, COG | Native | None | Values and sampling |
| COG overviews | Native | Nearest | Not read by the inspector |
| PNG tiles | Web Mercator | Nearest | Display only, stopping at the native-resolution zoom |
| Terrain tiles | Web Mercator | Bilinear | Display only |

Nothing is upsampled into a claimed finer product. Tile zoom is computed from the posting: z11 for 80 m data, and z12, the configured cap, for 20 m data.

## LOS conversion status

**Not implemented, deliberately.** The ATBD confirms the magnitude, φ = (4π/λ)·δr, and the file gives `centerFrequency`, so a wavelength can be obtained. Rev E gives the LOS unit vector as target to sensor. Neither document states which direction of range change gives positive phase, which acquisition is subtracted, or how the phase should be referenced. The brief forbids a displacement layer when these are unverified.

Needed before enabling: the [sign question](SCIENTIFIC_VALIDATION.md#open-questions) answered, a reference point method, and an independent test.

## Visualization

- Phase and offsets use a diverging scale, symmetric about the median of valid pixels, from the 2nd and 98th percentiles.
- Coherence and correlation peak use a fixed 0–1 scale.
- Display ranges are saved in the manifest and never change as the map moves.
- Tiles and legends use the same colour stops from one definition.
- Terrain hillshade is cosmetic and never sampled.

## Analysis against independent polygons

`analyse_pair.py` rasterises the UNOSAT polygons onto each frame's own grid and summarises valid pixels inside them, and in a ring within 1 km outside the mapped extent. Only medians and percentiles are reported, as description.

## LANDMET

`landmet.py` paints each equal-area cell onto a 1° raster, so a cell can cover several pixels, all holding its value. Nothing is interpolated. The file's metadata is unreliable, so each variable names its own scale key. Entirely empty variables are detected and shown as unavailable. Physically impossible values are flagged as masked and left unchanged. Tiles stop at zoom 3.

## Browse previews

If a science file cannot be retrieved, `prepare_previews.py` places the NISAR browse PNG on the map from the four corners in its KML. On the sample, those corners match the HDF5 grid within 0.002°. Previews are `renderable`, never `sampleable`, skip QA, and are labelled as pictures.

## Colour-only reference products

The EOS-RS damage proxy GeoTIFF stores RGBA colours, with no underlying values. It is displayed as supplied and is never sampled, because a number recovered from a colour would be invented.

## Simulations

`prepare_simulation.py` builds one file, `simulation.json`. The path starts at the UNOSAT detachment zone, joins the barrier lakes with straight lines, then takes the cheapest route along the OSM rivers, preferring the named main stem, and is resampled to one point per kilometre. River level at each point is the lowest Copernicus DEM value within about 120 m, kept from rising downstream. Each UNOSAT building, UNOSAT road piece, OSM road piece and OSM place within 2 km of the path stores its nearest kilometre and its height above that river level. The app only filters on those two numbers. The radar explainer computes coherence with the textbook formula on invented cells. See [LIMITATIONS.md](LIMITATIONS.md).
