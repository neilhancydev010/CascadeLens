# Data schema

There is no server API. The app reads static files. Types live in `frontend/src/types/manifest.ts`.

## Manifest

`frontend/public/data/manifests/manifest.json`

| Field | Meaning |
|---|---|
| `schemaVersion` | Currently 1. Other values are refused |
| `generatedAt` | ISO timestamp |
| `fixture` | True only for software tests. Shows a permanent banner |
| `fixtureLabel` | Banner text, used for the sample-file test |
| `caseStudy` | Identity, event date and search envelope |
| `bookmarks` | `id`, `name`, `bounds`, `basis`, and `anchor`, a named point selected with the bookmark |
| `groups` | Observation pairs and snapshots |
| `layers` | Every layer, usable or not |
| `granules` | Catalogue records with footprints and status |
| `analysis` | Results of `analyse_pair.py`, per pair. The story reads its figures from here |
| `controlSeries` | Rasuwa only. Median coherence inside the mapped mudflow against nearby ground, one entry per pair, with block-bootstrap 95% intervals and the valid share. `methodVersion` 2 is written by `prepare_control_series.py`; without it the medians come from an earlier script, and the app says so |
| `observability` | Radar observability per task and zone, from `prepare_observability.py` and `merge_observability.py`. The app shows its figures only when `methodVersion` is 2 or more. `frames` lists each frame assessed, with its pair, granules, incidence, sensitivity and the number of cells it decided; the top-level `frame`, `granule` and `sensitivity` are the first frame's |
| `observabilityViews` | Further viewing directions, keyed by view id (`t98`), from `prepare_observability.py --view`. Each has the same fields as `observability`, plus `label`, `layerIds` and `comparedWith`: per zone and task, the share usable from this view only, the main view only, both, either and neither. The views are never merged |
| `controlSeriesViews` | The control series from another viewing direction, keyed by view id, from `prepare_control_series.py --view` |
| `hazards` | Rasuwa only. Terrain screen and road exposure, from `prepare_hazards.py` |
| `access` | Rasuwa only. Summary of the road access screen, from `prepare_access.py`; the detail is in `data/access/<case>.json`, see [ACCESS_SCREEN.md](ACCESS_SCREEN.md) |
| `lake` | Tsho Rolpa only. GCOV lake area by date, coherence and the what-if scenario, from `prepare_lake.py` and `prepare_scenario.py`. Older builds also hold `motion`, which the app never shows |

Each case study has its own manifest, selected by `?case=`: `manifest.json` for Rasuwa (`rasuwa-2026`, the default) and `tsho-rolpa-2026.json` for Tsho Rolpa. The retired LANDMET case no longer ships; `processing/scripts/prepare_landmet.py` can rebuild it.

## Observation relationships

```text
group (pair-a) ──< layer (pair-a:gunw-phase) ──< source (frame 74, frame 75)
                                             └── qualityLayerIds -> layer (pair-a:gunw-coherence)
```

A group has `kind` of `pair` or `snapshot`. `available` is true only if one of its layers is usable. A layer belongs to at most one group. Terrain and reference layers have `groupId: null`.

## Layer status

| Status | Meaning | Selectable |
|---|---|---|
| `catalogued` | Listed by ASF, not retrieved | No |
| `downloaded` | File present, not processed | No |
| `inspected` | Read, gates not finished | No |
| `qa_passed` | Gates passed, not prepared | No |
| `prepared` | Assets ready; used for vector layers | Yes |
| `renderable` | Map tiles only, no values: the damage proxy and browse previews | Yes |
| `sampleable` | Tiles and sampling assets | Yes |
| `unavailable` | No record or no overlap | No |
| `invalid` | Failed inspection or QA | No |

A layer with several frames takes its worst frame's status. NISAR measurement layers go straight to `sampleable`, because the pipeline writes tiles and COGs together.

## Layer record

| Group | Fields |
|---|---|
| Identity | `id`, `groupId`, `name`, `category`, `measurementType`, `measurementClass`, `kind` |
| Source | `mission`, `instrument`, `productType`, `productMaturity`, `sourceGranules`, `attribution`, `page` |
| Observation | `acquisition`, `orbitDirection`, `track`, `frames`, `polarization` |
| Measurement | `units`, `unitsNote`, `postingM`, `crs`, `displayDb`, `goffLayer` |
| Assets | `sources[]`, `vector` |
| Quality | `qualityLayerIds`, `status`, `statusReason`, `limitations` |
| Display | `legend`, `stats` |
| Provenance | `processingHistory` |

`sources[]` holds `frame`, `granule`, `sourceFilename`, `sourceDataset`, `sha256`, `bounds`, `shape`, `validFraction`, `maskedFraction`, `sourceDtype`, `clipWindow`, `sampling`, `validity`, `tiles`, `maskTiles`. Picture layers have no `sampling` or `validity`.

`category` is `gunw`, `goff`, `gcov`, `terrain`, `reference`, `preview` or `gridded`. A `gridded` or `gunw` layer may have `timeSteps`, each with a `label` and its own `sources`, and may carry its own `explanation`. A label is a date (`2026-08-16`) or a radar pair (`2026-07-23/2026-08-16`); `rasuwa-2026:coherence-timeline`, from `prepare_timeline.py`, has one step per Track 48 frame 74 pair, and `rasuwa-2026:coherence-timeline-t98` (`--view t98`) one per Track 98 frame 16 pair. Road stretches made with `prepare_hazards.py --other-view` also carry `radarOtherView`, `radarOtherUsablePct`, `radarEitherUsablePct` and `radarWatchEither`. A preview sets `previewOf` to the view it belongs in. A `reference` layer is either a `vector` or a raster with `sources` and a `legend` with `lowLabel` and `highLabel`.

`processingHistory.provenance` records `pipelineVersion`, `configSha256`, `outputDtype`, `validityClasses`, `maskRule`, `tileResampling`, `nativeGridKept` and `displayTransform`. `measurementClass` is one of `measurement`, `derived`, `reference map`, `contextual`.

## Measurement inspector

```ts
samplePoint(layer, lng, lat): Promise<SampleResult>

interface SampleResult {
  state: 'valid' | 'masked' | 'nodata' | 'outside' | 'unavailable' | 'error'
  value?: number          // absent unless a stored number exists
  frame?: number | null
  granule?: string
  row?: number            // native pixel
  col?: number
  message: string
}
```

| State | Meaning | Value |
|---|---|---|
| `valid` | Passed every rule | Yes |
| `masked` | Stored value failed a quality rule | Yes, labelled |
| `nodata` | No valid observation here | No |
| `outside` | Outside the raster | No |
| `unavailable` | No sampling asset | No |
| `error` | Read failed | No |

Sampling takes the nearest native pixel, without interpolation. In a frame overlap, the first frame holding the best state is reported, which matches draw order. A failed read is retried up to three times, reopening the raster, before reporting `error`.

## Validity raster

UInt8 COG on the same grid as its measurement: 0 no data, 1 valid, 2 masked.

## Granule state

`data/metadata/granules/<file_id>.json` records `status`, `reason`, `checks`, `sha256`, `identification` and `validFraction`.
