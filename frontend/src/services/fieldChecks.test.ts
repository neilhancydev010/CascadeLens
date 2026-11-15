import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { Manifest } from '../types/manifest'
import type { RoadSegment } from './hazards'
import {
  addReport, CheckError, createFromRoad, load, merge, parseImport, persist, setStatus, STORAGE_KEY, toCsv, toGeoJson, toHtml, toJson, WARNING,
} from './fieldChecks'

// Field-check records are made from real shipped road stretches. No field report is invented: every report here is typed by the test.
const data = resolve(__dirname, '../../public/data')
const shipped = JSON.parse(readFileSync(resolve(data, 'manifests/manifest.json'), 'utf8')) as Manifest
const features = JSON.parse(readFileSync(resolve(data, 'vectors/road-exposure-rasuwa-2026.geojson'), 'utf8')).features as { geometry: { coordinates: [number, number][] }; properties: Omit<RoadSegment, 'distanceM'> }[]
const stretch = (i: number): RoadSegment => ({ ...features[i].properties, distanceM: 20, coordinates: features[i].geometry.coordinates })
const high = features.findIndex((f) => f.properties.exposure === 'High' || f.properties.exposure === 'Very high')
const NOW = new Date('2026-11-14T10:00:00Z')

describe('field-check records', () => {
  it('start from a real stretch, unverified, with its geometry, source file and a frozen copy of the satellite evidence', () => {
    const s = stretch(high)
    const c = createFromRoad(shipped, s, NOW)
    expect(c.id).toBe(`FV-rasuwa-2026-${s.id}`)
    expect(c.status).toBe('needs-verification')
    expect(c.reports).toEqual([])
    expect(c.geometry?.length).toBe(s.coordinates!.length)
    expect(c.triggeringEvidence).toContain(`road-exposure:${s.id}`)
    expect(c.satellite.radar.granule).toBe(shipped.observability?.granule)
    expect(c.unknown[0]).toMatch(/damaged, blocked, closed, safe or passable/)
    expect(c.why.length).toBeGreaterThan(0)
  })

  it('refuses a stretch with no stable ID', () => {
    expect(() => createFromRoad(shipped, { ...stretch(0), id: undefined })).toThrow(/no stable ID/)
  })

  it('never reaches Verified or Not confirmed without a field report', () => {
    const c = createFromRoad(shipped, stretch(high), NOW)
    expect(() => setStatus(c, 'verified')).toThrow(CheckError)
    expect(() => setStatus(c, 'not-confirmed')).toThrow(CheckError)
    expect(() => setStatus(c, 'closed', '  ')).toThrow(/reason/)
    expect(setStatus(c, 'assigned', '', 'District team', NOW)).toMatchObject({ status: 'assigned', assignee: 'District team' })
  })

  it('needs a finding, a source and a real past date for a field report', () => {
    const c = createFromRoad(shipped, stretch(high), NOW)
    const ok = { observedOn: '2026-11-10', source: 'Test source', finding: 'Test finding', outcome: 'verified' as const, independentlyConfirmed: false }
    expect(() => addReport(c, { ...ok, finding: ' ' }, NOW)).toThrow(/what was seen/)
    expect(() => addReport(c, { ...ok, source: '' }, NOW)).toThrow(/who or what/)
    expect(() => addReport(c, { ...ok, observedOn: '10/11/2026' }, NOW)).toThrow(/YYYY-MM-DD/)
    expect(() => addReport(c, { ...ok, observedOn: '2026-12-01' }, NOW)).toThrow(/future/)
  })

  it('adds a human report beside the satellite record without changing it', () => {
    const c = createFromRoad(shipped, stretch(high), NOW)
    const before = JSON.stringify(c.satellite)
    const next = addReport(c, { observedOn: '2026-11-10', source: 'Test source', finding: 'Test finding', outcome: 'not-confirmed', independentlyConfirmed: false }, NOW)
    expect(JSON.stringify(next.satellite)).toBe(before)
    expect(next.status).toBe('not-confirmed')
    expect(next.reports).toHaveLength(1)
    expect(next.reports[0].id).toBe(`${c.id}-R1`)
    expect(next.history.at(-1)).toMatchObject({ from: 'needs-verification', to: 'not-confirmed' })
    expect(c.reports).toHaveLength(0) // the original object is untouched
  })
})

describe('field-check storage and import', () => {
  it('round-trips through storage and survives a broken or blocked store', () => {
    const mem = new Map<string, string>()
    const store = { getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => { mem.set(k, v) } }
    const c = createFromRoad(shipped, stretch(high), NOW)
    expect(persist([c], store)).toBe(true)
    expect(load(store)).toEqual([c])
    mem.set(STORAGE_KEY, '{not json')
    expect(load(store)).toEqual([])
    expect(persist([c], { setItem: () => { throw new Error('quota') } })).toBe(false)
  })

  it('imports its own export and merges new field reports without duplicating', () => {
    const c = createFromRoad(shipped, stretch(high), NOW)
    const withReport = addReport(c, { observedOn: '2026-11-10', source: 'Test source', finding: 'Test finding', outcome: 'unable', independentlyConfirmed: false }, NOW)
    const incoming = parseImport(toJson([withReport], NOW))
    const once = merge([c], incoming)
    expect(once).toMatchObject({ added: 0, updated: 1 })
    expect(once.list[0].reports).toHaveLength(1)
    expect(merge(once.list, incoming)).toMatchObject({ added: 0, updated: 0 })
    expect(merge([], incoming)).toMatchObject({ added: 1 })
    expect(() => parseImport('{"records": []}')).toThrow(/not a CascadeLens/)
    expect(() => parseImport('nope')).toThrow(/not JSON/)
  })
})

describe('field-check exports', () => {
  const c = createFromRoad(shipped, stretch(high), NOW)
  it('carry the stretch ID, the source file and the warning in every format', () => {
    for (const text of [toJson([c], NOW), toGeoJson([c], NOW), toHtml([c], NOW)]) {
      expect(text).toContain(c.feature.id)
      expect(text).toContain(WARNING.slice(0, 40))
    }
    expect(toCsv([c])).toContain(c.feature.id)
    expect(toCsv([c])).toContain('Exposure is not damage or closure')
    expect(toCsv([c])).toContain(shipped.observability!.granule!)
  })
  it('export the real line geometry', () => {
    const g = JSON.parse(toGeoJson([c], NOW))
    expect(g.features[0].geometry.type).toBe('LineString')
    expect(g.features[0].geometry.coordinates.length).toBe(features[high].geometry.coordinates.length)
  })
  it('say plainly when nothing has been reported on the ground', () => {
    expect(toHtml([c], NOW)).toContain('Nothing on the ground has been reported')
    expect(toHtml([c], NOW)).not.toMatch(/<script/i)
  })
})
