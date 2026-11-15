import { describe, expect, it } from 'vitest'
import { coherence, count, elapsedMs, replayAdvance, type SimData, type SimProps } from './simulation'

const feature = (properties: SimProps) => ({ type: 'Feature' as const, properties, geometry: { type: 'Point' as const, coordinates: [0, 0] } })
const data = { features: { type: 'FeatureCollection', features: [
  feature({ k: 'c', km: 0, h: 0 }),
  feature({ k: 'b', km: 5, h: 10 }),
  feature({ k: 'b', km: 5, h: 40 }),
  feature({ k: 'b', km: 50, h: 10 }),
  feature({ k: 'a', km: 5, h: 90, len: 2 }),
  feature({ k: 'r', km: 5, h: 10, len: 3 }),
  feature({ k: 'p', km: 5, h: 10, name: 'Low' }),
  feature({ k: 'p', km: 5, h: 90, name: 'High' }),
] } } as unknown as SimData

describe('count', () => {
  it('the replay counts what was mapped as affected up to that point, at any height', () => {
    expect(count(data, 10)).toEqual({ buildings: 2, roadKm: 2, places: ['Low', 'High'] })
  })
  it('the what-if counts only what sits below the water and within reach', () => {
    expect(count(data, 10, 20)).toEqual({ buildings: 1, roadKm: 3, places: ['Low'] })
    expect(count(data, 60, 20).buildings).toBe(2)
  })
})

describe('elapsed time between frames', () => {
  it('is never negative when a frame is stamped earlier than a recorded moment', () => {
    expect(elapsedMs(1180, 1000)).toBe(180)
    expect(elapsedMs(1000, 1180)).toBe(0)
  })
})

describe('coherence', () => {
  it('is 1 on unchanged ground and falls as the ground changes', () => {
    expect(coherence(0)).toBeCloseTo(1)
    expect(coherence(0.5)).toBeLessThan(coherence(0.2))
    expect(coherence(1)).toBeLessThan(0.15)
  })
})

describe('replayAdvance', () => {
  it('never steps before the start, even when a frame timestamp precedes the start time', () => {
    const s = replayAdvance(0, -5, 198, 24)
    expect(s.km).toBe(0)
    expect(s.pos).toBe(0)
    expect(s.done).toBe(false)
  })
  it('moves in whole kilometres and stops exactly at the end', () => {
    expect(replayAdvance(0, 1000, 198, 24).km).toBe(8)
    expect(replayAdvance(197.5, 1000, 198, 24)).toEqual({ pos: 198, km: 198, done: true })
  })
})

// The exported table (data/qa/rasuwa-2026-simulation-features.csv) must re-count exactly what the app counts,
// so anyone can check a What-if setting with a spreadsheet filter.
describe('the What-if table reproduces count()', async () => {
  const { readFileSync } = await import('node:fs')
  const { resolve } = await import('node:path')
  const root = resolve(__dirname, '../../..')
  const data = JSON.parse(readFileSync(resolve(root, 'frontend/public/data/vectors/simulation.json'), 'utf8')) as SimData
  const [head, ...lines] = readFileSync(resolve(root, 'data/qa/rasuwa-2026-simulation-features.csv'), 'utf8').trim().split(/\r?\n/)
  const cols = head.split(',')
  // No field in this table holds a comma or a quote (place names are single words or hyphenated), so a plain split is exact
  const rows = lines.map((l) => Object.fromEntries(l.split(',').map((v, i) => [cols[i], v])))
  const byTable = (km: number, rise: number) => {
    const hit = rows.filter((r) => Number(r.km) <= km && Number(r.h) <= rise)
    return {
      buildings: hit.filter((r) => r.kind === 'b').length,
      roadKm: hit.filter((r) => r.kind === 'r').reduce((s, r) => s + Number(r.len), 0),
      places: hit.filter((r) => r.kind === 'p').map((r) => r.name),
    }
  }
  it('has one row per feature except the path itself', () => {
    expect(rows.length).toBe(data.features.features.filter((f) => f.properties.k !== 'c').length)
    expect(lines.every((l) => l.split(',').length === cols.length)).toBe(true)
  })
  for (const [rise, km, buildings, places] of [[25, 198, 3274, 8], [10, 74, 489, 1], [50, 35, 553, 2]] as const) {
    it(`rise ${rise} m, reach ${km} km`, () => {
      const app = count(data, km, rise)
      const table = byTable(km, rise)
      expect(table.buildings).toBe(app.buildings)
      expect(table.roadKm).toBeCloseTo(app.roadKm, 9)
      expect(table.places).toEqual(app.places)
      expect(app.buildings).toBe(buildings) // The figures written in docs/SCENARIO_WORKING.md
      expect(app.places.length).toBe(places)
    })
  }
})
