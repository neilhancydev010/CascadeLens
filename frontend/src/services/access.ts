import type { Manifest } from '../types/manifest'
import { assetUrl } from './manifest'

// Road access screen (prepare_access.py). Wording rule: results say "no road path in this network", never that a place is
// isolated or cut off, because footpaths, river crossings, helicopters and roads beyond the study area are not in the network.

export interface ClosedWay { way: string; name: string | null; highway: string; state: string; sources: string[] }
export interface AccessChange {
  change: 'unchanged' | 'longer' | 'other destination' | 'no path' | 'no path in either'
  km?: number; to?: string; beforeKm?: number; beforeTo?: string; detourKm?: number; reason?: string
  closedOnRoute?: ClosedWay[]
}
export interface AccessDetail {
  maturity: string
  network: { ways: number; km: number; vertices: number; destroyedWaysAdded: number }
  states: Record<string, { ways: number; km: number }>
  bridges: { reports: number; matched: unknown[]; unmatched: { name: string; status: string; nearestBridgeWayM: number | null }[]; matchWithinM: number }
  scenarios: { id: string; name: string; meaning: string; closedWays: number }[]
  healthDestinations: { amenities: string[]; why: string }
  healthChanges: Record<string, Record<string, AccessChange>>
  helipadChanges: Record<string, Record<string, AccessChange>>
  pieces: Record<string, string[][]>
  rules: Record<string, string>
  limitations: string[]
}

const cache = new Map<string, Promise<AccessDetail | null>>()
export function loadAccess(m: Manifest): Promise<AccessDetail | null> {
  const url = m.access?.url
  if (!url) return Promise.resolve(null)
  if (!cache.has(url)) cache.set(url, fetch(assetUrl(url)).then((r) => (r.ok ? r.json() : null)).catch(() => null))
  return cache.get(url)!
}

const closure = (w: ClosedWay) => `${w.name ?? `${w.highway} road ${w.way}`} (${w.sources.join('; ')})`

// One sentence per place and scenario. "what" names the destination type, such as "a health facility".
export function describe(c: AccessChange, what: string): string {
  switch (c.change) {
    case 'no path':
      return `No road path in this network to ${what}. Before: ${c.beforeKm} km to ${c.beforeTo}.${c.closedOnRoute?.length ? ` Closed on that route: ${c.closedOnRoute.map(closure).join('; ')}.` : ''}`
    case 'longer':
      return `${c.detourKm} km longer: ${c.km} km to ${c.to}, against ${c.beforeKm} km before.${c.closedOnRoute?.length ? ` Closed on the old route: ${c.closedOnRoute.map(closure).join('; ')}.` : ''}`
    case 'other destination':
      return `Now nearest by road: ${c.to}, ${c.km} km (before: ${c.beforeTo}, ${c.beforeKm} km).`
    case 'no path in either':
      return `No road path to ${what} in this network even with every mapped road open: a gap in the mapping or the network, not a closure.`
    default:
      return `Unchanged: ${c.km} km to ${c.to}.`
  }
}

// Closures across a set of affected places, each once, with how many of those places' old routes it sits on
export function closuresOf(entries: [string, AccessChange][]): { way: ClosedWay; places: string[] }[] {
  const by = new Map<string, { way: ClosedWay; places: string[] }>()
  for (const [name, c] of entries) for (const w of c.closedOnRoute ?? []) {
    if (!by.has(w.way)) by.set(w.way, { way: w, places: [] })
    by.get(w.way)!.places.push(name)
  }
  return [...by.values()].sort((a, b) => b.places.length - a.places.length || a.way.way.localeCompare(b.way.way))
}

export const closureLabel = (w: ClosedWay) => w.name ?? `${w.highway} road ${w.way}`

export function grouped(changes: Record<string, AccessChange>) {
  const by = (k: AccessChange['change'][]) => Object.entries(changes).filter(([, c]) => k.includes(c.change)).sort(([a], [b]) => a.localeCompare(b))
  return { lost: by(['no path']), longer: by(['longer', 'other destination']), never: by(['no path in either']), same: by(['unchanged']) }
}
