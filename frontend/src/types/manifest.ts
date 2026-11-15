// Schema documented in docs/API_AND_DATA_SCHEMA.md; written by processing/src/cascade_lens/manifest.py.
export type LayerStatus =
  | 'catalogued' | 'downloaded' | 'inspected' | 'qa_passed' | 'prepared' | 'renderable' | 'sampleable' | 'unavailable' | 'invalid'

export type Bounds = [number, number, number, number]

export interface RasterSource {
  frame: number | null
  granule: string
  sourceFilename: string
  sourceDataset?: string
  bounds: Bounds
  validFraction?: number
  maskedFraction?: number
  sampling?: string
  validity?: string
  tiles: { url: string; minzoom: number; maxzoom: number; count: number }
  maskTiles?: string
}

export interface VectorStyle {
  url: string
  type: 'fill' | 'line' | 'circle' | 'label'
  color?: string
  opacity?: number
  radius?: number
  dash?: boolean
  bounds: Bounds
  colorProperty?: string // per-feature colour, falling back to color
  width?: number
}

export interface Legend {
  type: 'continuous' | 'categorical'
  stops: string[]
  min?: number
  max?: number
  labels?: number[]
  unit?: string | null
  lowLabel?: string
  highLabel?: string
  keys?: { color: string; label: string }[]
}

export interface Stats {
  count: number
  min?: number
  max?: number
  mean?: number
  median?: number
  displayMin?: number
  displayMax?: number
  histogram?: { edges: number[]; counts: number[] }
  labels?: number[]
}

export interface TimeStep { label: string; sources: RasterSource[] }

export interface Layer {
  id: string
  groupId: string | null
  name: string
  category: 'gunw' | 'goff' | 'gcov' | 'terrain' | 'reference' | 'preview' | 'gridded'
  previewOf?: 'gunw' | 'goff' | 'gcov'
  mission: string
  instrument: string
  productType: string
  measurementClass: 'measurement' | 'derived' | 'reference map' | 'contextual'
  measurementType: string
  kind: 'continuous' | 'categorical' | 'vector'
  units: string | null
  unitsNote?: string
  acquisition: { reference: string; secondary: string | null }
  orbitDirection: string | null
  track: number | null
  frames: number[]
  postingM?: number[]
  crs?: string
  qualityLayerIds: string[]
  status: LayerStatus
  statusReason: string | null
  sources: RasterSource[]
  timeSteps?: TimeStep[] | null
  explanation?: { what: string; measures: string; inspect: string; establishes: string }
  vector?: VectorStyle
  stats?: Stats
  legend?: Legend
  polarization?: string[]
  displayDb?: boolean
  displayRelative?: boolean
  goffLayer?: number | null
  productMaturity: string
  sourceGranules: string[]
  processingHistory?: { processedAt: string; parameters: Record<string, unknown> }
  attribution: string
  limitations: string[]
  page?: string | null
}

export interface ObservationGroup {
  id: string
  kind: 'pair' | 'snapshot'
  label: string
  role: string
  direction: string
  track: number
  frames: number[]
  reference: string
  secondary: string | null
  products: string[]
  available: boolean
  statusReason: string | null
}

export interface ZoneSummary { pixels: number; validPct?: number; maskedPct?: number; median?: number | null }

export interface PairAnalysis {
  frames: Record<string, {
    ionosphere: { pearsonR: number; stdPhase: number; stdPhaseMinusIono: number }
    zones: Record<string, Record<string, ZoneSummary>>
  }>
}

export interface Bookmark {
  id: string
  name: string
  bounds: Bounds
  basis: string
  anchor?: { lng: number; lat: number; label: string }
}

export interface GranuleRecord {
  file_id: string
  group: string
  product: string
  frame: number
  direction: string
  track: number
  ref_date: string
  sec_date: string | null
  size_mb: number | null
  status: LayerStatus
  geometry: { type: string; coordinates: unknown } | null
}

export interface LakePoint {
  date: string
  areaKm2: number
  lowKm2: number
  highKm2: number
  validPct: number
  polarization: 'dual' | 'quad'
  nativePostingM: number
  outline: string
  image: string
  drape?: { rgb: string; hh: string }
  outlineFull?: string
}

export interface LakeTerrain {
  heights: string
  width: number
  height: number
  spacingM: number
  minM: number
  maxM: number
  lakeLevelM: number | null
  drapeSize: [number, number]
  source: string
  attribution: string
  note: string
  flowPath?: [number, number, number][]
  lakeSeed?: [number, number]
  outlet?: [number, number]
  drapeCoherence?: string
}

// Glacial lake cases only, written by processing/src/cascade_lens/lake.py.
export interface LakeSeries {
  name: string
  basin: string
  published?: string | null
  series: LakePoint[]
  imageSize: [number, number]
  imageMetres?: [number, number]
  terrain?: LakeTerrain | null
  changeKm2: number
  methodHalfRangeKm2: number
  method: string
  coherence?: LakeCoherence
  motion?: LakeMotion // written by older builds only; research output, never displayed
  scenario?: LakeScenario
}

// Written by processing/src/cascade_lens/motion.py add_coherence_layer: medians of one pair's coherence over the lake and the land.
export interface LakeCoherence { pair: [string, string]; granule: string; sourceDataset: string; maskApplied: boolean; lake: number; land: number; lakeValidPct?: number | null; landValidPct?: number | null }

// Written by processing/src/cascade_lens/scenario.py: what would happen IF the dam breached. Ranges, not predictions.
export interface LakeScenarioCase {
  breachM: number
  volumeM3: number
  peakM3s: Record<string, number>
  peakRange: [number, number]
  worstM3s: number
  arrival: [number, number, number][] // km, fastest minutes, slowest minutes
  depthM: [number, number, number][] // km, shallowest m, deepest m
  // Newer builds: the lake-area range carried through, the kinematic-wave sensitivity line and the floors counted
  volumeRangeM3?: [number, number]
  peaksByArea?: Record<'low' | 'mean' | 'high', Record<string, number>>
  arrivalKinematic?: [number, number, number][]
  floors?: { sections: number; slope: number; speedFast: number; speedSlow: number }
}
export interface LakeScenario {
  routeKm: number
  routeEnd: [number, number]
  lakeAreaKm2: number
  profile: [number, number][]
  marks: { km: number; lngLat: [number, number] }[]
  scenarios: LakeScenarioCase[]
  routeVector: string
  extentVector: string
  formulas: Record<string, string>
  roughness: [number, number]
  sectionEveryM: number
  bounds: [number, number, number, number]
  dem: string
  areaRangeKm2?: [number, number, number] // low, mean, high
  gammaNm3?: number
  slopeFloor?: number
  speedFloorMs?: number
  kinematicFactor?: number
  sectionsCsv?: string
}

// Older builds wrote movement bounds into the manifest. They are now research only (data/qa) and the app never shows them.
export interface LakeMotion {
  wavelengthCm: number
  zonesNote: string
  pair?: [string, string]
  coherenceLake?: number
  coherenceLand?: number
  dam?: { ok: boolean; reason?: string; pixels?: number; coherence?: number; differenceCm?: number; noiseCm?: number; limitCm?: number; detected?: boolean }
  damPairs?: ({ pair: [string, string] } & NonNullable<LakeMotion['dam']>)[]
  glacier: { track: number; frame: number; direction: string; dates: [string, string]; days: number; pixels: number; limitM: number; perYearM: number; detected: boolean }[]
}

export interface Manifest {
  schemaVersion: number
  generatedAt: string
  fixture: boolean
  fixtureLabel?: string | null
  analysis?: Record<string, PairAnalysis>
  caseStudy: { id: string; name: string; eventDate: string; searchEnvelope: Bounds }
  bookmarks: Bookmark[]
  groups: ObservationGroup[]
  layers: Layer[]
  granules: GranuleRecord[]
  lake?: LakeSeries
  controlSeries?: ControlSeries
  // the same comparison from another viewing direction, keyed by view id such as 't98'
  controlSeriesViews?: Record<string, ControlSeries & { label?: string }>
  observability?: Observability
  // further viewing directions (another track) beside the main block, keyed by view id such as 't98'; never merged into it
  observabilityViews?: Record<string, ObservabilityView>
  hazards?: Hazards
  access?: AccessSummary
}

// Written by processing/scripts/prepare_access.py. The detail (per-place results) is a separate file at url, fetched on demand.
export interface AccessSummary {
  url: string
  maturity: string
  states: Record<string, { ways: number; km: number }>
  summary: Record<string, { name: string; placesWithHealthPath: number; places: number; pieces: number }>
  limitations: string[]
}

export interface ObservabilityZone { name: string; pixels: number; percent?: Record<string, number>; verdict?: string; verdictRule?: string }

// Radar Observability block written by processing/scripts/prepare_observability.py
export interface Observability {
  pair: [string, string]
  baselinePair: [string, string] | null
  granule: string
  baselineGranule: string | null
  track: number
  frame: number
  orbit: string
  look: string
  compositeReleaseId: string
  productVersion: string
  incidenceDeg5to95: [number, number] | null
  postingM: number
  methodVersion?: number // absent before version 2, which applies the product masks; see services/observability.ts
  frames?: { frame: number; pair: [string, string]; baselinePair: [string, string] | null; granule: string; baselineGranule: string | null; cells: number }[]
  datasets?: Record<string, string>
  geometryNotAssessedPct?: number | null
  classes: Record<string, { code: number; label: string; color: string; meaning: string }[]>
  thresholds: Record<string, { value: number | string; provenance: string }>
  sensitivity?: { movementUsablePct: Record<string, number | null>; denominator: string; rule: string }
  sensitivityUsableMovementPct?: Record<string, number | null> // version 1 only, computed without the unwrapping rule
  limitations: string[]
  zones: Record<string, Record<string, ObservabilityZone>>
}

export interface ObservabilityComparison { name: string; pixels: number; onlyThis?: number; onlyOther?: number; both?: number; either?: number; neither?: number }

// One more viewing direction, written by prepare_observability.py --view. comparedWith holds, per zone and task, the share usable
// from this view only, the main view only, both, either and neither (same analysis grid; only "Usable" counts).
export interface ObservabilityView extends Observability {
  view: string
  label: string
  layerIds: string[]
  comparedWith?: { flags: string; note: string; zones: Record<string, Record<string, ObservabilityComparison>> }
}

// Coherence inside an affected zone against nearby control ground, one entry per real GUNW pair.
// Version 2 is written by processing/scripts/prepare_control_series.py; earlier versions came from a script that is not in the repository.
export interface ControlPair {
  pair: [string, string]; days: number; inside: number; outside: number; insideCi95: [number, number] | null; validPct: number; granule: string
  outsideCi95?: [number, number] | null; mode?: string | null; rangeBandwidthHz?: number | null
}
export interface ControlSeries {
  zone: string
  control: string
  track: number
  frame: number
  direction: string
  eventDate: string
  methodVersion?: number
  coherenceDataset?: string
  ciMethod?: string
  generator?: string
  pairs: ControlPair[]
}

// Terrain screen and road exposure, written by processing/scripts/prepare_hazards.py
export interface Hazards {
  terrain: { layerId: string; flags: Record<string, number>; classes: { code: number; label: string; color: string; meaning: string }[]; maturity: string
    validation: { kind?: string; caveats?: string[]; detachmentZone: { pixels: number; percentByClass: Record<string, number>; aucVsRestOfArea: number | null }; mudflowRunout: { percentByClass: Record<string, number>; note: string }; wholeArea: Record<string, number> } }
  roads: { layerId: string; kmByExposure: Record<string, { km: number; unwatchedKm: number; unwatchedEitherKm?: number }>; rules: Record<string, string>; maturity: string }
  dynamicTrigger: { maturity: string; needs: string[] }
}
