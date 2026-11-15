import type { Layer, Manifest } from '../types/manifest'
import { assetUrl, isUsable } from './manifest'

// Mirrors processing/src/cascade_lens/hazard.py
export const TFLAG = { slope15: 1, slope25: 2, slope35: 4, hollow: 8, wet: 16 } as const

export function terrainFactors(f: number): string[] {
  const out: string[] = []
  if (f & TFLAG.slope35) out.push('Very steep: 35° or more')
  else if (f & TFLAG.slope25) out.push('Steep: 25 to 35°')
  else if (f & TFLAG.slope15) out.push('Moderate slope: 15 to 25°')
  else out.push('Gentle: under 15°')
  if (f & TFLAG.hollow) out.push('A converging hollow, where water and debris collect')
  if (f & TFLAG.wet) out.push('Wet ground: many slopes drain through here')
  return out
}

export function terrainClass(f: number): number {
  const extra = (f & TFLAG.hollow ? 1 : 0) + (f & TFLAG.wet ? 1 : 0)
  if (f & TFLAG.slope35 && extra === 2) return 4
  if (f & (TFLAG.slope25 | TFLAG.slope35)) return extra ? 3 : 2
  if (f & TFLAG.slope15 && extra) return 2
  return 1
}

export const isTerrainScreen = (l: Layer) => l.measurementType === 'terrain-screen'
export const terrainLayer = (m: Manifest) => m.layers.find((l) => isTerrainScreen(l) && isUsable(l))
export const roadLayer = (m: Manifest) => m.layers.find((l) => l.measurementType === 'road-exposure' && isUsable(l))

// One 250 m stretch from prepare_hazards.py. id, osmId, name, bridge and the per-class radar shares exist from 13 Nov builds on.
export interface RoadSegment {
  road: string; exposure: string; color: string; reasons: string[]; steepSharePct: number | null; nearRiver: boolean; mapped2026: boolean
  radarWatch: string; radarUsablePct: number; radarHiddenPct: number; radarUnseenPct: number; lengthM: number; distanceM: number
  id?: string; osmId?: string | null; name?: string | null; bridge?: string | null; osmStatus?: string | null
  radarUnreliablePct?: number; radarNoValidPct?: number; radarOutsidePct?: number; radarNotAssessedPct?: number
  // a second viewing direction (prepare_hazards.py --other-view): its own usable share, and the share usable from either view
  radarOtherView?: string; radarOtherUsablePct?: number; radarEitherUsablePct?: number; radarWatchEither?: string
  // the stretch's own line from the shipped GeoJSON, kept so a field-check record can export the real geometry
  coordinates?: [number, number][]
}

type Seg = { geometry: { coordinates: [number, number][] }; properties: Omit<RoadSegment, 'distanceM'> }
const cache = new Map<string, Promise<Seg[]>>()

// Distance in metres from a point to a polyline, on a local flat approximation (fine at these scales).
export function distanceM(p: [number, number], line: [number, number][]): number {
  const kx = 111320 * Math.cos((p[1] * Math.PI) / 180), ky = 110540
  let best = Infinity
  for (let i = 1; i < line.length; i++) {
    const ax = (line[i - 1][0] - p[0]) * kx, ay = (line[i - 1][1] - p[1]) * ky
    const bx = (line[i][0] - p[0]) * kx, by = (line[i][1] - p[1]) * ky
    const dx = bx - ax, dy = by - ay
    const t = dx || dy ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy))) : 0
    best = Math.min(best, Math.hypot(ax + t * dx, ay + t * dy))
  }
  return best
}

export async function nearestRoad(m: Manifest, p: [number, number], withinM = 150): Promise<RoadSegment | null> {
  const l = roadLayer(m)
  if (!l?.vector) return null
  const url = l.vector.url
  if (!cache.has(url)) cache.set(url, fetch(assetUrl(url)).then((r) => r.json()).then((fc) => (Array.isArray(fc?.features) ? fc.features as Seg[] : [])).catch(() => []))
  let best: RoadSegment | null = null
  for (const s of await cache.get(url)!) {
    const d = distanceM(p, s.geometry.coordinates)
    if (d <= withinM && (!best || d < best.distanceM)) best = { ...s.properties, distanceM: Math.round(d), coordinates: s.geometry.coordinates }
  }
  return best
}
