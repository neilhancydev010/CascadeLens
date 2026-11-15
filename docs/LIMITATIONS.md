# Limitations

## Current build

NISAR measurements of the event are loaded, but they are Provisional. Rasuwa GCOV snapshots are not downloaded; the Tsho Rolpa case uses GCOV. Nothing here calculates displacement.

## Rebuilt with the corrected method

All outputs were rebuilt from the raw files on 13 November 2026, with the product's own mask applied and frames 74 and 75 both assessed. The first observability method, which ignored the mask and reported a change as visible on 66% of the detachment zone, is withdrawn. The rebuild also fixed a decoding error in the mask: it is a 32-bit field, and its digits were read from the whole number. That moved about 0.1 percentage point of frame 75.

## Coverage gaps

Pair A holds no usable measurement at the detachment zone. The product's own mask marks every pixel there as having no valid subswath in the 28 August acquisition (mask value 10), a gap in that acquisition's coverage; it is not water. Pair B, from the opposite side (Track 98), reaches the source with valid data: a change could be judged on 35% of it, the rest being hidden by layover or already incoherent before the event, and movement on none of it. Frame 75 covers the lower mudflow and the Trishuli corridor; 14% of the mudflow and 18% of the Trishuli corridor lie outside both frames.

## Coherence is not a damage map

Coherence inside the mapped extent is much lower than nearby, and channels may be low anyway. One pre-event pair has been compared, reproducibly. Inside the mapped mudflow, median coherence fell from 0.38 to 0.19 across the event while the ground around it rose from 0.40 to 0.50. That is consistent with surface change there, but it does not establish the cause. The comparison is indicative only: the pair before spans 24 days and the event pair 12, and they were acquired in different radar modes. From the opposite side (Track 98) every pair has the same mode, and the gap also opens (0.31 against 0.40 before, 0.13 against 0.49 across), but that pair before is also 24 days long. In Track 98 the control ground itself drops to 0.31 by early October, so the control area changes too.

## Derived phase

The ionosphere-removed layer is calculated here. Its sign was chosen from the ATBD equation and confirmed by scatter, not from a stated convention. The screen is low-frequency only, and troposphere and terrain effects remain.

## Observation interval

A pair shows that something changed between two dates, at most. The 12-day interval cannot establish when a change happened. It cannot separate the 26 August event from other changes in that time.

## Orbit geometry

Ascending and descending passes view slopes from opposite sides. Pair A and Pair B are not a time series, and the 28 and 31 August GCOV snapshots are not a before and after. CascadeLens does not subtract them. Observability is judged for each direction on its own; "either track" figures only count where at least one direction could judge, and never mix reasons from the two.

## InSAR decorrelation

Steep terrain, snow, vegetation, water and surface disruption all reduce coherence. Phase may be unusable exactly where the event was strongest. Low coherence is not proof of a landslide or a measure of its extent.

## Phase interpretation uncertainty

Interferometric phase is not displacement. Converting it needs a verified sign convention and reference, and CascadeLens has neither yet. Phase also includes atmospheric, ionospheric and other effects. The ionosphere layer is not applied.

## GOFF outliers

Pixel offsets are raw, unculled and unfiltered. Range and azimuth components are radar-geometry measurements, not east, west, north or south movement. Gross-outlier flagging could also flag real large motion.

## Spatial resolution

GUNW and GOFF are posted at 80 m. Small features such as narrow channels, roads or single buildings may not be resolved.

## GCOV backscatter

Backscatter is not automatically a damage or flood classification. Meaning depends on the observation and the comparison method.

## Preliminary external reference data

UNOSAT layers are preliminary satellite analyses that the source records as not yet field validated. They are not ground truth. One layer has an unresolved date inconsistency. OSM data is community-maintained, and it may predate or postdate the event.

## Sentinel-1 reference layers

These are not NISAR measurements. Sentinel-1 is a C-band mission, while NISAR's L-band radar senses the surface differently. The EOS-RS map is preliminary, may be unreliable over vegetated or mountainous areas, and holds colours rather than values. The REACH screening measures backscatter change, not structural damage, and covers only areas around pre-event buildings.

## Browse previews

If the fallback is used, a preview is a picture placed from four corners. It holds no measurements and has not been quality checked.

## Tsho Rolpa movement

The app does not show movement of the moraine dam or the glacier. Earlier builds gave a dam movement limit in centimetres and a glacier limit extrapolated to metres per year, from 12-day pairs. Those bounds are now research output only (`prepare_lake.py --research-motion`, written to `data/qa`). The research test refuses thin reference areas, unreliable labels and a missing centre frequency, and nothing is extrapolated to a yearly rate. The app keeps the coherence layer, which shows where the surface stayed the same, not how far anything moved.

## Retired LANDMET test case

The LANDMET case was taken out of the app on 6 November 2026. Its processing script and tests remain. It was a 2007 global weather dataset at about 110 km resolution, not radar data, unrelated to the 2026 event, and its licence is not stated in the file.

## Provisional products

NISAR products in this period are PROVISIONAL. NASA's general definition says such products are not intended for scientific research, and ASF lists known issues. Reprocessing is planned once the products are validated.

## Lack of field verification

CascadeLens has no field data. Nothing here confirms what happened on the ground.

## Coverage

Pair A's frames cover 80% of the Trishuli bookmark by footprint. Valid-pixel coverage is unknown. Terrain stops at the catalogue search envelope.

## Not a forecasting system

CascadeLens is retrospective. It has no forecasting model, rainfall, geology, hydrology or ground sensors, and nothing in it has been calibrated or validated for prediction. The what-if simulation below is a rough illustration, not a forecast. It must not be used for warnings or safety decisions.

## Simulations

These are illustrations and contain no NISAR measurements.

- **Flow replay:** the path is geometry, not a mapped flow line. It follows OSM rivers, and its first part joins the detachment zone, barrier lakes and upper Lende Khola with straight lines, because no channel is mapped there. The speed is invented, and nothing shows when the flow reached any place.
- **What-if flood:** a feature counts as reached if its Copernicus DEM ground height is within the chosen rise above the nearest river point and within the chosen distance. It ignores water volume, speed, valley shape, sediment and the fall of a flood downstream, and it has not been compared with any real flood. The DEM has a 30 m grid and vertical error, so narrow gorges are poorly resolved. Only buildings UNOSAT mapped as affected are counted, so the app cannot say how many other buildings a flood would reach.
- **Tsho Rolpa dam-breach scenario:** the breach depths (10, 20 and 30 m) are assumed, and nobody can say whether or when the dam will fail. The three published peak-flow formulas differ about tenfold. The lake walls are taken as vertical, which slightly overestimates the volume. Arrival times come from Manning's equation on 60 m terrain cross-sections every 500 m, with an assumed roughness. Two simplifications pull the times in opposite directions and are not corrected: the front moves at the water speed rather than the faster flood-wave speed (about 5/3 of it in a wide channel, which would make every time 40% shorter), and the peak is never reduced downstream (which makes far times too early and far depths too high). So the times are not reliably early or late. Rock and mud in the flow, landslides it could trigger, and bridges or dams are not included. Every cross-section is published in `data/qa/tsho-rolpa-2026-scenario-sections.csv` and the working is in [SCENARIO_WORKING.md](SCENARIO_WORKING.md).
- **Cliff impact (Hypothesis):** a mentor's account, by oral communication, with no location or figures. The candidate sites come from a 30 m terrain model made before the event, which smooths narrow gorges, and from UNOSAT's preliminary extent, whose edge on steep walls is not a measured flood line. The speeds are what the superelevation and run-up formulas give from those inputs, not measurements. A straight-stretch control shows a one-sided offset of about 9 m and a wide scatter, so no site stands out clearly. CascadeLens tests where it could have happened. It does not confirm that it did. See `data/qa/rasuwa-2026-impact-sites.md`.
- **Time replay:** plays stored values in order, for any layer with saved time steps (today the four Tsho Rolpa GCOV dates). Nothing is interpolated between saved times.
- **Radar explainer:** a teaching model on invented ground. It is not NISAR processing, and its slider is not a measure of anything real.
