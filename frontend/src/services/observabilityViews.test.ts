import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { Manifest } from '../types/manifest'
import { buildStory } from '../data/story'
import { isUsable } from './manifest'
import { obsViews } from './observability'
import { toHtml, type Report } from './report'

// A second viewing direction (Track 98, ascending) beside the main one (Track 48). Each is judged from its own reason flags.
const shipped = JSON.parse(readFileSync(resolve(__dirname, '../../public/data/manifests/manifest.json'), 'utf8')) as Manifest

describe('observability from two viewing directions', () => {
  it('groups layers by their own flag raster, main view first, never reading one view through another', () => {
    const views = obsViews(shipped.layers.filter(isUsable))
    expect(views.map((v) => v.label)).toEqual(['Track 48, descending, frames 74 and 75', 'Track 98, ascending, frame 16'])
    for (const v of views) {
      expect(new Set(v.layers.map((l) => l.sources[0].sampling)).size).toBe(1)
      expect(v.layers.map((l) => l.measurementType).sort()).toEqual(['observability-disturbance', 'observability-movement'])
    }
    expect(views[0].layers[0].sources[0].sampling).not.toBe(views[1].layers[0].sources[0].sampling)
  })

  it('keeps the second view beside the main block, with its own pairs and a per-zone comparison', () => {
    const v = shipped.observabilityViews?.t98
    expect(v?.track).toBe(98)
    expect(v?.pair).toEqual(['2026-08-19', '2026-08-31'])
    expect(v?.baselinePair).toEqual(['2026-07-26', '2026-08-19'])
    expect(shipped.observability?.track).toBe(48)
    for (const task of ['disturbance', 'movement']) {
      for (const [id, c] of Object.entries(v!.comparedWith!.zones[task])) {
        const total = (c.onlyThis ?? 0) + (c.onlyOther ?? 0) + (c.both ?? 0) + (c.neither ?? 0)
        expect(Math.abs(total - 100), `${task} ${id}`).toBeLessThanOrEqual(0.3)
        expect(c.either).toBeCloseTo((c.onlyThis ?? 0) + (c.onlyOther ?? 0) + (c.both ?? 0), 0)
        expect(c.either!).toBeGreaterThanOrEqual(v!.zones[task][id].percent!.Usable - 0.1)
      }
    }
  })

  it('tells the story of the second view only from its own numbers', () => {
    const step = buildStory(shipped).find((s) => s.id === 'observability')!
    const v = shipped.observabilityViews!.t98
    const src = v.zones.disturbance['vector:unosat_detachment_zone.geojson'].percent!.Usable
    const text = step.paragraphs.join(' ')
    expect(text).toContain(`From the other side (${v.label}`)
    expect(text).toContain(`a surface change could be judged on ${src.toFixed(0)}% of the detachment zone`)
    expect(text).toContain('where the first direction could judge none of it')
    const source = buildStory(shipped).find((s) => s.id === 'source')!.paragraphs.join(' ')
    expect(source).toMatch(/Its coherence there is very low: the median is 0\.\d\d at the detachment zone/)
    expect(source).not.toMatch(/proves|caused by/i)
  })

  it('compares before and after from the opposite side only from its own series, and says when the radar mode is the same', () => {
    const cs = shipped.controlSeriesViews!.t98
    const before = cs.pairs[0], across = cs.pairs[1]
    expect(cs.pairs.every((p) => p.mode === '4000')).toBe(true)
    const text = buildStory(shipped).find((s) => s.id === 'radar')!.paragraphs.join(' ')
    expect(text).toContain('From the opposite side (Track 98, ascending), every pair was acquired in the same radar mode (4000)')
    expect(text).toContain(`${before.inside.toFixed(2)} against ${before.outside.toFixed(2)} nearby`)
    expect(text).toContain(`across the event it was ${across.inside.toFixed(2)} against ${across.outside.toFixed(2)}`)
    expect(text).toContain('Both directions show the gap opening across the event.')
    expect(text).toContain(`The pre-event pair still spans ${before.days} days against ${across.days}.`)
    const flat = { ...shipped, controlSeriesViews: { t98: { ...cs, pairs: [before, { ...across, inside: before.inside, outside: before.outside }] } } }
    expect(buildStory(flat).find((s) => s.id === 'radar')!.paragraphs.join(' ')).toContain('From this side the gap does not open across the event.')
  })

  it('prints each view in the report, each with its own pair and answers', () => {
    const view = (frame: string, answer: string) => ({ pair: 'a to b', frame, methodVersion: 2, current: true, answers: [{ question: 'Q?', answer }], reasons: [] })
    const r: Report = {
      title: 'T', generatedAt: '2026-11-13T00:00:00.000Z', case: { id: 'rasuwa-2026', name: 'Rasuwa', eventDate: '2026-08-26' }, point: { lng: 85.3, lat: 28.1 },
      observability: view('Track 48, descending, frames 74 and 75', 'No valid data in the product'), otherViews: [view('Track 98, ascending, frame 16', 'Usable')],
      readings: [], explanations: [], notes: [],
    }
    const h = toHtml(r)
    expect(h).toContain('Track 48, descending, frames 74 and 75')
    expect(h).toContain('Track 98, ascending, frame 16')
    expect(h.indexOf('No valid data in the product')).toBeLessThan(h.indexOf('<td>Usable</td>'))
    expect(h).toContain('Each viewing direction is judged on its own flags.')
  })
})
