import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { Manifest } from '../types/manifest'
import type { RoadSegment } from './hazards'
import { toCsv, toGeoJson, toHtml, type Report } from './report'
import { roadEvidence } from './roadEvidence'

// P0.3 acceptance: one road stretch can be explained from the panel, and every export carries the same values.
const data = resolve(__dirname, '../../public/data')
const shipped = JSON.parse(readFileSync(resolve(data, 'manifests/manifest.json'), 'utf8')) as Manifest
const stretches = (JSON.parse(readFileSync(resolve(data, 'vectors/road-exposure-rasuwa-2026.geojson'), 'utf8')).features as { properties: Omit<RoadSegment, 'distanceM'> }[])
  .map((f) => ({ ...f.properties, distanceM: 40 }) as RoadSegment)

const find = (test: (s: RoadSegment) => boolean) => {
  const s = stretches.find(test)
  if (!s) throw new Error('no shipped stretch matches')
  return s
}

const report = (road: ReturnType<typeof roadEvidence>): Report => ({
  title: 'T', generatedAt: '2026-11-13T00:00:00.000Z', case: { id: 'rasuwa-2026', name: 'Rasuwa', eventDate: '2026-08-26' }, point: { lng: 85.3, lat: 28.1 },
  observability: null, readings: [], explanations: [], hazards: { terrain: null, road, maturity: 'Experimental screens, not forecasts' }, notes: [],
})

describe('road-segment evidence', () => {
  it('names every shipped stretch with a unique, stable ID from its OSM way', () => {
    const ids = stretches.map((s) => s.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids.every((i) => /^(way|node|relation)\/\d+:\d+$|^geom-[0-9a-f]{12}:\d+$/.test(i ?? ''))).toBe(true)
  })

  it('states the radar pair, dates, source file and method behind the rating', () => {
    const ev = roadEvidence(shipped, find((s) => s.exposure === 'High'))
    expect(ev.radar.pair).toBe('16 Aug 2026 to 28 Aug 2026')
    expect(ev.radar.baseline).toBe('23 Jul 2026 to 16 Aug 2026')
    expect(ev.radar.trackFrame).toBe('Track 48 descending, frames 74 and 75')
    expect(ev.radar.granule).toBe(shipped.observability!.granule)
    expect(ev.radar.methodVersion).toBe(2)
    expect(ev.radar.current).toBe(true)
    expect(ev.radar.otherView?.label).toBe('Track 98, ascending')
    expect(ev.radar.otherView?.pair).toBe('19 Aug 2026 to 31 Aug 2026')
    expect(ev.radar.otherView!.eitherPct).toBeGreaterThanOrEqual(Math.max(ev.radar.otherView!.usablePct, ev.radar.shares[0].pct ?? 0) - 0.1)
    expect(ev.verify.join(' ')).not.toContain('withdrawn first observability method')
  })

  it('accounts for the whole stretch across the observability classes', () => {
    for (const s of stretches) {
      const total = roadEvidence(shipped, s).radar.shares.reduce((a, x) => a + (x.pct ?? 0), 0)
      expect(Math.abs(total - 100), s.id).toBeLessThanOrEqual(0.6)
    }
  })

  it('turns each factor into something a reviewer can check, and never calls a Low stretch safe', () => {
    const bridge = roadEvidence(shipped, find((s) => Boolean(s.bridge)))
    expect(bridge.verify.join(' ')).toContain('bridge is standing and passable')
    const unseen = roadEvidence(shipped, find((s) => (s.radarEitherUsablePct ?? s.radarUsablePct) < 20))
    expect(unseen.verify.join(' ')).toContain('Neither viewing direction could watch most of this stretch, so radar can neither confirm nor rule out')
    const rescued = roadEvidence(shipped, find((s) => s.radarUsablePct < 20 && (s.radarEitherUsablePct ?? 0) >= 50))
    expect(rescued.verify.join(' ')).toContain('with the opposite side (Track 98, ascending)')
    expect(rescued.radar.shares[0].pct).toBeLessThan(20) // the main pair's own share is never replaced by the other view's
    const low = roadEvidence(shipped, find((s) => s.exposure === 'Low'))
    expect(low.verify.join(' ')).toContain('does not mean the road is safe')
    const mapped = roadEvidence(shipped, find((s) => s.mapped2026))
    expect(mapped.verify.join(' ')).toContain('not field validated')
  })

  it('writes the same values into the printable page, the CSV and the GeoJSON as the panel shows', () => {
    const ev = roadEvidence(shipped, find((s) => s.exposure === 'High' && s.nearRiver))
    const r = report(ev)
    const html = toHtml(r)
    for (const v of [ev.id!, ev.osmWay!, `${ev.exposure} exposure`, ev.radar.pair!, ev.radar.granule!, ...ev.reasons, ...ev.context, ...ev.verify,
      ...ev.radar.shares.map((s) => `${s.pct}%`)]) expect(html, v).toContain(v.replace(/&/g, '&amp;'))
    const csv = toCsv(r).trim().split('\r\n')
    expect(csv).toHaveLength(2)
    expect(csv[1]).toContain(ev.id!)
    expect(csv[1]).toContain(`${ev.exposure} exposure; ${ev.radar.watch}`)
    expect(csv[1]).toContain(String(ev.radar.shares[0].pct))
    expect(JSON.parse(toGeoJson(r)).features[0].properties.hazards.road).toEqual(ev)
  })
})
