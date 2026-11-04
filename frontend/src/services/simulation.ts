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

export interface SimView { data: SimData; mode: 'replay' | 'whatif'; km: number; rise: number }

export async function loadSimulation(path: string): Promise<SimData> {
  const res = await fetch(assetUrl(path))
  if (!res.ok) throw new Error(`Simulation data request failed with HTTP ${res.status}`)
  return res.json()
}

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
