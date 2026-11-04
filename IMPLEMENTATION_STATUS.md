# Implementation status

**Status: the minimum scientific MVP threshold is met.** The product runs real NISAR measurements of the Rasuwa event, offline, from a one-click package. It is a first prototype on Provisional data, and its limits below are real.

Report date: 2026-11-01.

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

- **GCOV snapshots** are not downloaded. They need 31 GB, and the tab says so.
- **GSLC** is deferred: no justified use yet.
- **Displacement** is deliberately absent, because the phase sign convention is undocumented.
- **No pre-event control pair** has been compared, so low coherence is not yet tested against the channel's normal state.
- **No field validation** exists, and the data is Provisional.
- **Not tested** on another computer, a physical phone, or a hosted server. Browser tests ran in Microsoft Edge and Brave, not Chrome, Firefox or Safari. The code has been reviewed for Firefox and Safari problems, but never run in them.
- **The app cannot run from `index.html` directly.** Browsers block that, and the page now explains what to do.
- **Not created:** a public repository, submission links or a hosted deployment.

## Feature status

| Feature | Implementation | Test status | Data status | Notes |
|---|---|---|---|---|
| Catalogue discovery | Implemented and tested | Run live against ASF | Real: 140 granules | |
| QA pre-check before download | Implemented and tested | Run on real granules | Real | `--qa-only` |
| NISAR download | Implemented and tested | Real downloads | Real: 6 granules, 9.2 GB | Size check after download |
| HDF5 inspection | Implemented and tested | Real files | Real | |
| GUNW extraction | Implemented and tested | Real files | Real | Pair A |
| GOFF extraction | Implemented and tested | Real files | Real | Pairs A and B |
| GCOV extraction | Implemented and tested | NASA sample file | Unavailable dependency | 31 GB not downloaded |
| Ionosphere-removed phase | Implemented and tested | Real files | Real, derived | Labelled as calculated here |
| Analysis against UNOSAT polygons | Implemented and tested | Real files | Real | Descriptive only |
| Browse-preview fallback | Implemented and tested | Real PNG and KML | Not needed now | Section 24 emergency mode |
| GSLC integration | Deferred | None | Catalogued only | |
| LOS displacement | Deliberately not implemented | Test asserts no such layer | n/a | |
| QA gates | Implemented and tested | Real files, pass and fail cases | Real | |
| Provenance records | Implemented and tested | Automated | Real | |
| COG and tile export | Implemented and tested | Real files | Real | |
| Manifest from disk state | Implemented and tested | Integration checks | Real | |
| Application shell, map | Implemented and tested | 31 browser tests | Real | |
| Case-study selector | Implemented and tested | Browser | Real | Rasuwa and LANDMET |
| Bookmarks | Implemented and tested | Browser, exact values | Real | Approximate navigation frames |
| Observation-pair selector | Implemented and tested | Browser | Real | |
| Dual-evidence switching | Implemented and tested | Browser | Real | Keeps the selected point |
| Measurement inspector | Implemented and tested | Unit and browser tests | Real | All six result states |
| Quality overlays, masked pixels | Implemented and tested | Browser, fixture | Real | |
| Legends, explanations | Implemented and tested | Browser | Real | |
| Story mode | Implemented and tested | Browser | Real | Figures read from the analysis |
| Snapshot view | Implemented and tested | Browser, fixture | Unavailable dependency | Shows *Download required* for Rasuwa |
| Simulate mode (flow replay, what-if flood, radar explainer) | Implemented and tested | Unit, data and browser tests | Illustrations built on real geography | Not a forecast, see [LIMITATIONS.md](docs/LIMITATIONS.md) |
| Time slider, day chart | Implemented and tested | Browser | Real, LANDMET | |
| Terrain, UNOSAT, OSM, boundaries | Implemented and tested | Browser | Real | |
| Sentinel-1 proxy and screening | Implemented and tested | Browser | Real, preliminary | |
| LANDMET test case | Implemented and tested | Real file, browser | Real, test only | |
| Offline operation | Implemented and tested | CSP-enforced browser test | Real | |
| One-click package | Implemented and tested | Fresh unzip, via the `.bat` | Real | Needs Python 3 |
| Accessibility | Implemented and tested | axe, keyboard | n/a | No serious findings |
| Responsive layout | Implemented and tested | 375 px emulation | n/a | Not on a physical phone |
| Image swipe comparison | Deferred | None | n/a | Optional |
| Public repository, deployment | Not implemented | None | n/a | Team decision |

## Commands executed and results

```text
python -m pytest tests                       105 passed
npx tsc --noEmit                             no errors
npm test                                     29 passed
npx playwright test                          31 passed: 21 on the real build, 10 on the synthetic fixture
python processing/scripts/process_nisar.py   6 granules qa_passed
python processing/scripts/generate_manifest.py   29 layers: 14 sampleable, 12 prepared, 2 catalogued, 1 renderable
python processing/scripts/prepare_landmet.py     19 layers: 12 sampleable, 7 unavailable; peak 12.92 h local solar time
```

**Total: 165 automated tests passing.** Before the Simulate mode was added, the real-build browser tests also passed against the final package, unzipped fresh and started through `Start CascadeLens.bat`, in both Microsoft Edge and Brave. The Simulate test ran in Edge and Brave against the build.

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
| Pair B, 19→31 Aug, Track 98 ascending | GOFF | 15, 16 | Validated by the QA gates |
| Snapshots 28 and 31 Aug | GCOV | 74, 75, 15, 16 | Not downloaded |

"Validated" means these gates passed. The products themselves remain NASA Provisional. Pair B frame 15 does not reach the mapped extent.

## Findings

See [SCIENTIFIC_VALIDATION.md](docs/SCIENTIFIC_VALIDATION.md).

- Coherence is much lower along the mapped channel: 0.19 and 0.16 inside, against 0.46 and 0.52 nearby.
- Pair A has no data at the detachment zone: a swath gap.
- Pair B reaches it, and matching largely fails: correlation peak 0.18 against 0.63.
- Raw phase is dominated by the ionosphere.
- Pixel offsets show no large coherent shift.

These are descriptive evidence, not proof of cause.

## Bugs found by real data, and fixed

GOFF units check, ignored GOFF mask, unreliable phase shown as valid, GCOV mask flag, hardcoded maturity, no-data pixels drawn as valid on the map, and the washed-out phase scale. Browser testing also found a worker failure, a page-blanking race, intermittent first reads, and error messages hidden behind the map. Opening `index.html` directly also gave a silent blank page, and it now explains what to do. All are fixed, and details are in [SCIENTIFIC_VALIDATION.md](docs/SCIENTIFIC_VALIDATION.md).

## Remaining actions

See [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md). The most valuable next step is a pre-event control pair.
