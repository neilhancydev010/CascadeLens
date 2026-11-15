# Implementation status

**Status: the minimum scientific MVP threshold is met.** The product runs real NISAR measurements of the Rasuwa event, offline, from a one-click package. It is a first prototype on Provisional data, and its limits below are real.

Report date: 2026-11-10, updated 2026-11-13 for the scientific corrections of 12 November (P0.1) and the rebuild from the raw files. Two main cases now ship: Rasuwa (flagship, opens first) and Tsho Rolpa glacial lake.

> **Rebuilt on 13 November 2026.** Both cases were rebuilt from the raw NISAR files with the P0.1 code: observability method 2 over frames 74 and 75, the control series with bootstrap intervals, the hazard screens on the new flags, and coherence through time. The rebuild found and fixed one more error, in reading the product's mask (S13). The raw files are not in the repository; the steps are in [docs/RADAR_OBSERVABILITY.md](docs/RADAR_OBSERVABILITY.md).
>
> **Second viewing direction (13 November).** Track 98 (ascending, frame 16) is loaded as Pair B GUNW, with four more pairs: observability as its own view beside Track 48, the before/after series in one radar mode, coherence through time, and road stretches watched from either direction.

## Minimum completion threshold (brief, section 25.4)

| # | Requirement | Met? | Evidence |
|---|---|---|---|
| 1 | One real NISAR-derived analytical layer works | Yes | GUNW phase and coherence, from real granules |
| 2 | A second complementary layer works | Yes | GOFF offsets, SNR and correlation peak, in two pairs |
| 3 | Geographic navigation works | Yes | Browser tests |
| 4 | Acquisition metadata is correct | Yes | Read from the files, and matched to the catalogue and brief |
| 5 | Users can inspect actual valid measurements | Yes | Inspector values match source arrays |
| 6 | The product explains what information means | Yes | Per-layer explanations |
| 7 | Scientific limitations are visible | Yes | Shown for every layer |
| 8 | Processing is reproducible from source data | Yes | Rerun from raw files; determinism tested |
| 9 | Main experience can be demonstrated locally | Yes | Tested from a fresh unzip, with outside requests blocked |

## What is not done

- **Rasuwa GCOV snapshots** are not downloaded. They need 31 GB, and the tab says so. The Tsho Rolpa case does use GCOV.
- **GSLC** is deferred: no justified use yet.
- **Displacement** is deliberately absent, because the phase sign convention is undocumented.
- **Parts of the study area lie outside both Track 48 frames**: 14% of the mapped mudflow, 18% of the Trishuli corridor and 19% of the whole case area. Track 98 frame 16 covers all of it, from the other side.
- **No landslide or flood warning.** The one model run on real data, the rainfall threshold (L2), did not beat chance in 2025-2026 (corridor CSI 0.20, chance 95th percentile 0.21). The susceptibility and river models wait for a geological map and DHM discharge. See [MODELS.md](docs/MODELS.md).
- **BIPAD's licence is not established.** Its landslide reports are used for the threshold run but not redistributed; NDRRMA has to confirm terms.
- **Not built from the November master prompt** (need data or are out of scope): river-flow context (GloFAS), a rainfall map layer (IMERG Late is on disk for the threshold model, but not drawn in the app), live processing, hosting. Slope screening and road exposure were built on 10 November as experimental screens. Machine-learning landslide prediction and calibrated flood probabilities are deliberately not attempted.
- **No field validation** exists, and the data is Provisional.
- **Not tested** on another computer, a physical phone, or a hosted server. Browser tests ran in Microsoft Edge and Brave up to 2 November, and in Chromium from 10 November. They have not run in Chrome, Firefox or Safari. The code has been reviewed for Firefox and Safari problems, but never run in them.
- **The app cannot run from `index.html` directly.** Browsers block that, and the page now explains what to do.
- **The Space Apps rules have not been checked.** On 13 November 2026, spaceappschallenge.org answered 503 or could not be reached from the cloud environment, so the submission requirements and judging criteria were not read.
- **Not created:** a public repository, submission links or a hosted deployment.

## Feature status

| Feature | Implementation | Test status | Data status | Notes |
|---|---|---|---|---|
| Catalogue discovery | Implemented and tested | Run live against ASF | Real: 140 granules | |
| QA pre-check before download | Implemented and tested | Run on real granules | Real | `--qa-only` |
| NISAR download | Implemented and tested | Real downloads | Real: 6 granules, 9.2 GB; the rebuild added 5 GUNW granules | Size check and SHA-256 after download; resumes with a range request |
| HDF5 inspection | Implemented and tested | Real files | Real | |
| GUNW extraction | Implemented and tested | Real files | Real | Pair A |
| GOFF extraction | Implemented and tested | Real files | Real | Pairs A and B |
| GCOV extraction | Implemented and tested | NASA sample file, Tsho Rolpa files | Real for Tsho Rolpa | Rasuwa GCOV (31 GB) not downloaded |
| Ionosphere-removed phase | Implemented and tested | Real files | Real, derived | Labelled as calculated here |
| Analysis against UNOSAT polygons | Implemented and tested | Real files | Real | Descriptive only |
| Browse-preview fallback | Implemented and tested | Real PNG and KML | Not needed now | Section 24 emergency mode |
| GSLC integration | Deferred | None | Catalogued only | |
| LOS displacement | Deliberately not implemented | Test asserts no such layer | n/a | |
| QA gates | Implemented and tested | Real files, pass and fail cases | Real | |
| Provenance records | Implemented and tested | Automated | Real | |
| COG and tile export | Implemented and tested | Real files | Real | |
| Manifest from disk state | Implemented and tested | Integration checks | Real | |
| Application shell, map | Implemented and tested | 29 browser tests | Real | An error boundary keeps a failing panel from blanking the app |
| Case-study selector | Implemented and tested | Browser | Real | Rasuwa and Tsho Rolpa |
| Bookmarks | Implemented and tested | Browser, exact values | Real | Approximate navigation frames |
| Observation-pair selector | Implemented and tested | Browser | Real | |
| Dual-evidence switching | Implemented and tested | Browser | Real | Keeps the selected point |
| Measurement inspector | Implemented and tested | Unit and browser tests | Real | All six result states |
| Quality overlays, masked pixels | Implemented and tested | Browser, fixture | Real | |
| Legends, explanations | Implemented and tested | Browser | Real | |
| Story mode | Implemented and tested | Browser | Real | Figures read from the analysis |
| Snapshot view | Implemented and tested | Browser, fixture | Unavailable dependency | Shows *Download required* for Rasuwa |
| Simulate mode (flow replay, what-if flood, radar explainer) | Implemented and tested | Unit, data and browser tests | Illustrations built on real geography | Not a forecast, see [LIMITATIONS.md](docs/LIMITATIONS.md) |
| Time slider, day chart | Implemented and tested | Unit (labels), browser | Real: Tsho Rolpa GCOV dates, Rasuwa coherence pairs | Any layer with saved time steps; labels show dates or pair dates |
| Coherence through time (P0.5) | Implemented and tested (13 Nov) | Python, unit, browser | Real: five Track 48 pairs over frames 74 and 75 (23 Jul to 3 Oct 2026) and five Track 98 frame 16 pairs (26 Jul to 6 Oct) | Two layers, `rasuwa-2026:coherence-timeline` and `-t98`, built by `prepare_timeline.py`; Time replay picks the series; the inspector chart shows a clicked spot pair by pair |
| Terrain, UNOSAT, OSM, boundaries | Implemented and tested | Browser | Real | |
| Sentinel-1 proxy and screening | Implemented and tested | Browser | Real, preliminary | |
| LANDMET test case | Retired from the app (team decision, 6 Nov); data no longer shipped (13 Nov) | Pipeline tests only, with the file present | Real, test only | `prepare_landmet.py` can rebuild it |
| Offline operation | Implemented and tested | CSP-enforced browser test | Real | |
| One-click package | Implemented and tested | Fresh unzip, via the `.bat`; `start.sh` run on Linux only; the no-Python path (`serve.ps1`) is checked on a Windows runner in CI, with a small stand-in app, not the full package | Real | macOS and Linux need Python 3. Windows needs nothing installed |
| Accessibility | Implemented and tested | axe, keyboard | n/a | No serious findings |
| Responsive layout | Implemented and tested | 375 px emulation, with the story's place checked to be in view | n/a | Not on a physical phone |
| Evidence classes on every layer | Implemented and tested | Unit, browser | Real | Observed, Derived, Forecast, Hypothesis, Reference, Scenario, Unknown |
| Radar Observability ("Can the radar see it?") | Method version 2 implemented, tested and rebuilt (13 Nov) | Python, frontend, browser | Real, derived | Applies the product's own mask. Rasuwa over frames 74 and 75, Tsho Rolpa over frame 74; see [RADAR_OBSERVABILITY.md](docs/RADAR_OBSERVABILITY.md) |
| Second viewing direction, Track 98 (13 Nov) | Implemented and tested | Python (comparison, merge, frames per product), unit, browser | Real: Pair B GUNW frame 16 and its pre-event pair | Its own observability view (`observabilityViews.t98`), compared cell by cell with Track 48 and never merged; the inspector and report answer per direction |
| Pre-event control comparison | Implemented, tested and rebuilt (13 Nov) | Python, unit | Real, derived, with block-bootstrap 95% intervals; Track 48 and Track 98 | Rasuwa story step 2 chart. Wording: consistent with surface change, not proof of cause |
| "What could explain this?" | Implemented and tested | Unit, browser | Real inputs, rule-based | Reads each viewing direction (Track 48 and Track 98) from its own flags and pair, and labels each check with its track. Counts only radar values at the spot and independent mapping. Labels: Fits the checks, Partly fits, Little support; never probabilities |
| Evidence report (PDF, CSV, GeoJSON, JSON) | Implemented and tested | Unit, browser downloads and print | Real | Built in the browser |
| Tsho Rolpa dam and glacier movement | Research output only (12 Nov) | Python | Not shown in the app | `prepare_lake.py --research-motion` writes to `data/qa` |
| Tsho Rolpa coherence layer | Rebuilt (13 Nov) | Python | Real, event pair | `prepare_lake.py --coherence-only` rebuilds it without GCOV. The mask marks most of the lake as water, so the story quotes no lake median |
| Landslide-prone terrain screen (Model A) | Experimental | 5 Python, 2 unit, browser | Real DEM, derived | Rasuwa only; a one-event consistency check (AUC 0.66), not a validation |
| Road-segment evidence inspector (P0.3) | Implemented and tested | Unit (panel and exports agree), browser (panel ID matches the downloaded JSON) | Real OSM + NISAR, derived | Stable stretch IDs, radar pair and source file, per-reason shares, what to verify |
| Road access to health care (P0.4) | Experimental | 12 Python on synthetic networks, unit, browser | Real OSM + HOT bridge reports, derived | See [ACCESS_SCREEN.md](docs/ACCESS_SCREEN.md); stops at the study area |
| Road exposure screen | Experimental | Unit, browser | Real OSM + DEM + NISAR, derived | Says whether the radar could watch each stretch, from the version 2 flags, and the share watched from Track 98 and from either direction |
| Readiness engine (P1) | Implemented and tested | 18 Python, 3 unit, browser | Files on disk, with SOURCE.json | See [READINESS.md](docs/READINESS.md): 2 context only, 2 data available but processing required (L2: BIPAD's licence; L4: the NISAR series), 8 not available, each with its next requirement. A validation that misses its own criterion does not count |
| First models and verification harness (P2) | Implemented and tested; the rainfall threshold run on real data | 23 Python | Real: IMERG Late 2016 to 2026; BIPAD reports (licence not stated) | L1 and F3 still blocked: geology, DHM discharge. See [MODELS.md](docs/MODELS.md) |
| Rainfall-triggered landslide risk (Model B, L2) | Run on real data; missed its pre-stated criterion | 6 Python (events, scoring, readiness rule), unit | Real, derived | Held-out 2025-2026 corridor CSI 0.20 against a chance 95th percentile of 0.21 (p = 0.12). Held at *data available* until BIPAD's licence is confirmed |
| First-minute finding card | Implemented and tested | Unit, browser | Real, figures read from the manifest | |
| Status registry (`frontend/public/data/status.json`) | Implemented and tested | Unit test checks every "complete" claim names a test that calls its computation | n/a | Shown in the app as "What is real?" |
| Claim register (`frontend/public/data/claims.json`) | Implemented and tested | Unit test keeps the wording of RED claims off every live surface | n/a | 30 claims: 25 from the Stage 0 audit, one added at the rebuild, two with the Track 98 view and two with the rainfall-threshold run (C29, and C30 as a guard against claiming landslide warnings), with basis and status |
| Image swipe comparison | Implemented | No automated test | Real, Tsho Rolpa GCOV dates | Tsho Rolpa compare mode |
| Public repository, deployment | Not implemented | None | n/a | Team decision |

## Commands executed and results

### Review fixes merged from main (13 Nov)

A separate review of `main` on 13 November found the problems below. Its fixes are merged into this branch, and they now run on every pull request, see `.github/workflows/ci.yml`.

| Problem | Effect | Fix |
|---|---|---|
| The report's "Print or save as PDF" button did nothing in the packaged app | The offline policy blocks a script written into the report window | The app wires the button from outside; browser test added |
| On a phone, the story's sheet covered the place its text describes | The detachment zone sat under the sheet | The map frames each place in the strip above the sheet; the sheet is shorter with one row of buttons; browser test added |
| On a phone, the story's map could be left undrawn | Headless Chromium treated the solid scrolling sheet as hiding the whole map | The sheet's background stops just short of solid. Seen only in headless Chromium, and not checked on a physical phone |
| On a phone, the case menu, "What is real?" and the dam-failure scenario could not be reached | The top bar hides them at that width | The Layers sheet now carries them |
| On `main`, pressing Play in the flow replay could blank the whole app on a busy computer | The first animation frame can be stamped earlier than the moment Play was pressed, which made the position negative | This branch had already fixed the replay (`replayAdvance`). The merge adds the same guard to the four other animations, and a fault anywhere now shows a message with a restart button instead of a blank page |
| The chosen tab's label vanished under the pointer | White text on the white pill, straight after the click | Hover rule corrected; browser test added |
| The opening finding card stayed over the map while the reader explored | It hid the map behind the inspector's readings | It steps aside once a place, layer or spot is picked |
| A package built on Linux shipped a Windows launcher with Unix line endings | `.bat` files can misread their labels that way | `.gitattributes` fixes the endings; `start.sh` added for macOS and Linux |

After the rainfall-threshold run, on 2026-11-13, in a fresh cloud copy without the raw NISAR files, in Chromium:

```text
python -m pytest tests                       173 passed, 35 skipped (skips need the raw NISAR files, NASA's samples or the LANDMET file)
npx tsc --noEmit                             no errors
npm test                                     99 passed
npm run build                                OK
npx playwright test                          32 passed (22 on the real build, 10 on the synthetic fixture)
python processing/scripts/run_rain_thresholds.py   corridor CSI 0.203, chance 95th percentile 0.2085, p 0.12: criterion not met
```

The Python total is lower than the 182 below only because this copy has no raw NISAR files, so their tests skip.

After the later frame 75 pairs were added, on 2026-11-13, in a cloud copy, in Chromium:

```text
python -m pytest tests                       182 passed, 24 skipped (skips need NASA's samples or the LANDMET file)
npx tsc --noEmit                             no errors
npm test                                     98 passed
npm run build                                OK
npx playwright test                          32 passed
```

Earlier the same day: with the explanations from both directions, Python 181 passed, unit 98, browser 32; when the second viewing direction (Track 98) was added, Python 181, unit 92, browser 31.

After the rebuild from the raw files, earlier the same day:

```text
python -m pytest tests                       173 passed, 24 skipped (skips need NASA's samples or the LANDMET file;
                                             the 11 real-data Rasuwa tests ran on the raw granules and passed)
npx tsc --noEmit                             no errors
npm test                                     86 passed
npm run build                                OK
npx playwright test                          30 passed
```

Earlier on 2026-11-13, with the P0.1 code and the shipped (not yet rebuilt) data, in Chromium:

```text
python -m pytest tests                       92 passed, 35 skipped (skips need raw granules, NASA samples or the LANDMET file)
npx tsc --noEmit                             no errors
npm test                                     62 passed
npm run build                                OK
npx playwright test                          28 passed, 1 failed: the fixture test "a failed raster source reports an error"
                                             passed 3 of 3 when re-run alone, so it is intermittent (likely the flaky fixture test, E4)
```

Passing tests check the code's behaviour. They do not validate a scientific result, and the real-data tests that need raw granules were skipped.

Later on 2026-11-13, after the P0.2 to P2 work on the same branch: Python 158 passed, 35 skipped; type check clean; unit 81 passed; browser 30 passed. The finished package was then built, unzipped fresh, started with its own `serve.py` (what `Start CascadeLens.bat` runs) and tested with `CL_BASE_URL`: all 20 real-data browser tests passed under the offline policy. The `.bat` was not run, because there is no Windows machine here.

Re-run on 2026-11-10 in a cloud copy (Chromium, not Edge or Brave):

```text
python -m pytest tests                       72 passed, 35 skipped (skips need the raw NISAR files)
npx tsc --noEmit                             no errors
npm test                                     52 passed
npx playwright test                          29 passed
python processing/scripts/prepare_hazards.py 689 road segments, 179 tiles, 29 s
```

The skeptical review and the scorecard are in [REVIEW_AND_SCORECARD.md](docs/REVIEW_AND_SCORECARD.md). Capability maturity lives in one place, `frontend/public/data/status.json`.

The Rasuwa Simulate tab, dropped when Tsho Rolpa was added on 3 to 4 Nov, is back. The LANDMET test case stays out of the app (team decision, 6 Nov), so its tests were replaced by a Tsho Rolpa to Rasuwa case-switch test.

Results from 2026-11-01, kept for reference:

```text
python -m pytest tests                       105 passed
npm test                                     29 passed
npx playwright test                          31 passed: 21 on the real build, 10 on the synthetic fixture
python processing/scripts/process_nisar.py   6 granules qa_passed
python processing/scripts/generate_manifest.py   29 layers: 14 sampleable, 12 prepared, 2 catalogued, 1 renderable
python processing/scripts/prepare_landmet.py     19 layers: 12 sampleable, 7 unavailable; peak 12.92 h local solar time
```

On 2026-11-01, 165 automated tests passed. Before the Simulate mode was added, the real-build browser tests also passed against the final package, unzipped fresh and started through `Start CascadeLens.bat`, in both Microsoft Edge and Brave. The Simulate test ran in Edge and Brave against the build.

| Performance, 2026-11-02, packaged app in headless Edge | Before | After |
|---|---|---|
| Map ready | 0.89 s | 0.60 s |
| Map ready, CPU slowed 4× | 3.83 s | 1.69 s |
| Sample after a click | 0.11 s | 0.13 s |
| First script file | 1.9 MB | 0.4 MB |

These are medians of 3 localhost runs, not hosted or low-bandwidth measurements. Headless browsers draw the map in software, so compare the two columns rather than reading them as real-use times.

## Product files

| Group | Product | Frames | Status |
|---|---|---|---|
| Pair A, 16→28 Aug, Track 48 descending | GUNW | 74, 75 | Validated by the QA gates |
| Pair A | GOFF | 74, 75 | Validated by the QA gates |
| Pair B, 19→31 Aug, Track 98 ascending | GUNW | 16 | Validated by the QA gates (13 Nov) |
| Pair B | GOFF | 15, 16 | Validated by the QA gates |
| Series, before and after the event | GUNW | Track 48: 74 (and 75 before); Track 98: 16 | Validated by the QA gates (13 Nov) |
| Snapshots 28 and 31 Aug | GCOV | 74, 75, 15, 16 | Not downloaded |

"Validated" means these gates passed. The products themselves remain NASA Provisional. Pair B frame 15 does not reach the mapped extent, so its GUNW is not used.

## Findings

See [SCIENTIFIC_VALIDATION.md](docs/SCIENTIFIC_VALIDATION.md).

- Coherence is much lower along the mapped channel: 0.19 and 0.16 inside, against 0.46 and 0.52 nearby.
- Pair A holds no usable measurement at the detachment zone. The product's own mask gives every frame-74 pixel there the value 10: no valid subswath in the 28 August acquisition, a gap in that acquisition's coverage, not water. Two earlier statements went too far. The first called it a swath gap without checking the mask. The 6 November correction said a change was visible on 66% of it, which came from an observability check that ignored the mask.
- Against a pre-event pair (23 Jul to 16 Aug), median coherence in the mapped mudflow went from 0.38 to 0.19 while nearby ground went from 0.40 to 0.50; across the event the two 95% intervals do not overlap. The gap narrowed over the three later pairs (0.315 against 0.550, then 0.434 against 0.545, then 0.456 against 0.537). That is consistent with surface change in the mapped area, not proof of cause. The pairs differ in length (24 and 12 days) and radar mode.
- Where the radar could judge: in the whole Rasuwa case area, a change was judgeable on 44.0% and movement on 48.1%; on the Bhote Koshi corridor, 64.0% and 72.5%.
- Pair B (Track 98, the opposite side) reaches the source: coherence 0.09 against 0.46 nearby, and matching largely fails (correlation peak 0.18 against 0.63). A change could be judged on 35% of the detachment zone from that side, movement on none of it. Across the whole case area, a change is judgeable from at least one direction on 78.8%.
- From Track 98, every pair has the same radar mode, and the mudflow's coherence gap also opens across the event: 0.31 against 0.40 before, 0.13 against 0.49 across.
- Road stretches the radar could not watch, counting either direction: 4.8 km (2.7 km of them High exposure), against 28.2 km from Track 48 alone.
- Raw phase is dominated by the ionosphere.
- Pixel offsets show no large coherent shift.

These are descriptive evidence, not proof of cause.

## Bugs found by real data, and fixed

GOFF units check, ignored GOFF mask, unreliable phase shown as valid, GCOV mask flag, hardcoded maturity, no-data pixels drawn as valid on the map, and the washed-out phase scale. Browser testing also found a worker failure, a page-blanking race, intermittent first reads, and error messages hidden behind the map. Opening `index.html` directly also gave a silent blank page, and it now explains what to do. The 13 November rebuild found that the mask decoder read the water and subswath digits from the whole 32-bit value instead of its low byte (S13); on the event pair that wrongly kept 0.14 to 0.15% of pixels. The time-step chart also labelled every Tsho Rolpa date "20". All are fixed, and details are in [SCIENTIFIC_VALIDATION.md](docs/SCIENTIFIC_VALIDATION.md).

## Remaining actions

See [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md). The rebuild, the second viewing direction and the later frame 75 pairs are done. The most valuable next steps need new data: rainfall and river data for the models, and a 12-day pre-event pair. The download list is kept with the project files.
