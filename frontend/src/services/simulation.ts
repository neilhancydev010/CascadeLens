import type { FeatureCollection, Geometry } from 'geojson'
import { assetUrl } from './manifest'

export type SimKind = 'c' | 'b' | 'a' | 'r' | 'p' // Channel, UNOSAT building, UNOSAT road, OSM road, OSM place

export interface SimProps { k: SimKind; km: number; h: number; len?: number; name?: string }

export interface SimData {
  path: [number, number, number][] // lng, lat, river level in metres. The index is the distance in km.
  places: { name: string; km: number; h: number }[]
  features: FeatureCollection<Geometry, SimProps>
  totals: { buildings: number; buildingsAll: number; mappedRoadKm: number; roadKm: number }
}

// Candidate cliff-impact sites, written by processing/scripts/find_impact_sites.py. Hypothesis only.
export type ImpactOutcome = 'supports a hard outer-bank impact' | 'does not show it' | 'cannot judge'
export interface ImpactSite {
  id: string; km: number; lng: number; lat: number; turn_deg: number; outer_side: string; on_mapped_river: number
  rc_m: number | null; b_m: number | null; river_m: number; wall_slope_deg: number; wall_height_m: number; inner_slope_deg: number; sections: number
  dh_raw_m: number | null; control_m: number; dh_m: number | null; h_up_outer_m: number | null; h_up_inner_m: number | null
  v_super_k5_ms: number | null; v_super_k1_ms: number | null; v_runup_min_ms: number | null
  coh_outer_median: number | null; coh_inner_median: number | null; s1_change_outer_pct: number | null; s1_change_inner_pct: number | null
  outcome: ImpactOutcome; reasons: string
}
export interface ImpactSites {
  evidenceClass: 'Hypothesis'; source: string
  thresholds: { turnDeg: number; withinKm: number; wallSlopeDeg: number; wallReachM: number; demNoiseM: number; minResolvedM: number; k: [number, number] }
  control: { leftMinusRightM: number; sections: number; p25M: number; p75M: number }
  features: { type: 'Feature'; geometry: { type: 'Point'; coordinates: [number, number] }; properties: ImpactSite }[]
}
export const IMPACT_COLOURS: Record<ImpactOutcome, string> = { 'supports a hard outer-bank impact': '#ff7f66', 'does not show it': '#7fd1c7', 'cannot judge': '#9a93b8' }

export interface SimView { data: SimData; mode: 'replay' | 'whatif' | 'impact'; km: number; rise: number; impact?: ImpactSites; selected?: string }

export async function loadImpactSites(path = 'data/vectors/impact_sites.json'): Promise<ImpactSites> {
  const res = await fetch(assetUrl(path))
  if (!res.ok) throw new Error(`Impact sites request failed with HTTP ${res.status}`)
  return res.json()
}

export async function loadSimulation(path: string): Promise<SimData> {
  const res = await fetch(assetUrl(path))
  if (!res.ok) throw new Error(`Simulation data request failed with HTTP ${res.status}`)
  return res.json()
}

// Time since the last animation frame, never negative. A frame's timestamp is when the browser began that frame, and on a busy computer
// that can be earlier than a moment already recorded with performance.now(). Unclamped, the first step of an animation then runs backwards.
export const elapsedMs = (now: number, before: number) => Math.max(0, now - before)

export interface SimCount { buildings: number; roadKm: number; places: string[] }

// A feature counts once the flow has passed its kilometre. Without a rise, that is everything mapped so far.
export function count(data: SimData, km: number, rise?: number): SimCount {
  const out: SimCount = { buildings: 0, roadKm: 0, places: [] }
  for (const { properties: p } of data.features.features) {
    if (p.km > km || (rise !== undefined && p.h > rise)) continue
    if (p.k === 'b') out.buildings++
    else if (p.k === (rise === undefined ? 'a' : 'r')) out.roadKm += p.len ?? 0
    else if (p.k === 'p') out.places.push(p.name!)
  }
  return out
}

export const SIM_CELLS = 100
const noise = (i: number) => { const x = Math.sin(i * 127.1) * 43758.5453; return x - Math.floor(x) }

// Each ground cell's echo on the first pass, and how far the second pass shifts it. `change` runs from 0 to 1.
export const firstPass = (i: number) => noise(i + 1000) * 2 * Math.PI
export const shift = (i: number, change: number) => (noise(i) * 2 - 1) * Math.PI * change

// The textbook measure: 1 when every cell shifts alike, near 0 when the shifts are random.
export function coherence(change: number) {
  let re = 0
  let im = 0
  for (let i = 0; i < SIM_CELLS; i++) {
    re += Math.cos(shift(i, change))
    im += Math.sin(shift(i, change))
  }
  return Math.hypot(re, im) / SIM_CELLS
}

// One animation frame of the flow replay: whole kilometres along the path, never outside it.
// A frame's timestamp can come before the moment the replay started, so a negative elapsed time counts as no time.
export function replayAdvance(pos: number, elapsedMs: number, last: number, seconds: number): { pos: number; km: number; done: boolean } {
  const next = Math.max(0, pos) + (Math.max(0, elapsedMs) / 1000) * (last / seconds)
  if (!(next < last)) return { pos: last, km: Math.max(0, last), done: true }
  return { pos: next, km: Math.min(last, Math.max(0, Math.floor(next))), done: false }
}
