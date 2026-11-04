import type { Layer, LayerStatus, Manifest } from '../types/manifest'

const USABLE: LayerStatus[] = ['prepared', 'renderable', 'sampleable']

// String concat, not new URL(): URL encodes the {z}/{x}/{y} placeholders MapLibre needs to find.
export const assetUrl = (path: string) => document.baseURI.replace(/[^/]*$/, '') + path

export const isUsable = (l: Layer) => USABLE.includes(l.status) && Boolean(l.sources.length || l.vector)

// `simulation` is the file from prepare_simulation.py. Simulate offers only what a case's data can support, see docs/ADDING_DATA.md.
export const CASES: { id: string; label: string; file: string; simulation?: string }[] = [
  { id: 'rasuwa-2026', label: 'Rasuwa 2026 (NISAR)', file: 'manifest.json', simulation: 'data/vectors/simulation.json' },
  { id: 'landmet-2007', label: 'LANDMET test, 31 Dec 2007', file: 'landmet.json' },
]

export function currentCase(search = window.location.search) {
  const id = new URLSearchParams(search).get('case')
  return CASES.find((c) => c.id === id) ?? CASES[0]
}

export async function loadManifest(url = assetUrl(`data/manifests/${currentCase().file}`)): Promise<Manifest> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Manifest request failed with HTTP ${res.status}`)
  const m = (await res.json()) as Manifest
  if (m.schemaVersion !== 1 || !Array.isArray(m.layers)) throw new Error('Manifest has an unsupported schema')
  return m
}

// What each pipeline status means to someone reading the layer list. Statuses are not interchangeable.
export const STATUS_LABEL: Record<LayerStatus, string> = {
  catalogued: 'Download required',
  downloaded: 'Quality assessment pending',
  inspected: 'Quality assessment pending',
  qa_passed: 'Awaiting preparation',
  prepared: 'Available',
  renderable: 'Map only',
  sampleable: 'Available',
  unavailable: 'Layer unavailable',
  invalid: 'Failed validation',
}

export const formatDate = (iso: string) =>
  /^\d{4}-\d{2}-\d{2}$/.test(iso)
    ? new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
    : iso

export function acquisitionLabel(l: Pick<Layer, 'acquisition'>) {
  const { reference, secondary } = l.acquisition
  return secondary ? `${formatDate(reference)} → ${formatDate(secondary)}` : formatDate(reference)
}

// Products write dimensionless as "1" or "unitless". Neither means anything to a reader.
export const unitLabel = (u: string | null | undefined) => (!u || u === '1' || u === 'unitless' ? '' : u)

export const coordinates = (lng: number, lat: number) =>
  `${Math.abs(lat).toFixed(5)}°${lat < 0 ? 'S' : 'N'}, ${Math.abs(lng).toFixed(5)}°${lng < 0 ? 'W' : 'E'}`

export function posting(l: Layer) {
  if (!l.postingM) return '—'
  const m = Math.abs(l.postingM[0])
  return m >= 10000 ? `about ${Math.round(m / 1000)} km` : `${Math.round(m)} m`
}
