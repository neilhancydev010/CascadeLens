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

Each case study has its own manifest: `manifest.json` for Rasuwa and `landmet.json` for LANDMET, selected by `?case=`.

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

`category` is `gunw`, `goff`, `gcov`, `terrain`, `reference`, `preview` or `gridded`. A `gridded` layer may have `timeSteps`, each with a `label` and its own `sources`, and may carry its own `explanation`. A preview sets `previewOf` to the view it belongs in. A `reference` layer is either a `vector` or a raster with `sources` and a `legend` with `lowLabel` and `highLabel`.

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
