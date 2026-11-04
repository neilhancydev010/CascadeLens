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
}
