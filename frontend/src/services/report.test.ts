import { describe, expect, it } from 'vitest'
import { toCsv, toGeoJson, toHtml, type Report } from './report'

const r: Report = {
  title: 'T <x>', generatedAt: '2026-11-06T02:00:00.000Z', case: { id: 'rasuwa-2026', name: 'Rasuwa', eventDate: '2026-08-26' }, point: { lng: 85.3, lat: 28.1 },
  observability: { pair: 'a to b', frame: 'Track 48, frame 74', methodVersion: 2, current: true, answers: [{ question: 'Q?', answer: 'Usable' }], reasons: [] },
  readings: [{ layer: 'Coherence, "HH"', layerId: 'pair-a:gunw-coherence', evidence: 'Observed', state: 'valid', value: 0.21, units: '1', observation: 'x', source: 'G' },
    { layer: 'Phase', layerId: 'p', evidence: 'Observed', state: 'nodata', value: null, units: 'radians', observation: 'x', source: null }],
  explanations: [{ id: 'd', title: 'Disturbed', standing: 'Partly fits', for: ['a'], against: [], context: ['steep'], missing: ['m'] }],
  notes: ['n'],
}

describe('evidence report', () => {
  it('writes one CSV row per layer, quoting commas and quotes, with blanks for no value', () => {
    const lines = toCsv(r).trim().split('\r\n')
    expect(lines).toHaveLength(3)
    expect(lines[1]).toContain('"Coherence, ""HH"""')
    expect(lines[2]).toContain(',nodata,,radians,')
  })
  it('writes a point feature that keeps only real values', () => {
    const g = JSON.parse(toGeoJson(r))
    expect(g.features[0].geometry.coordinates).toEqual([85.3, 28.1])
    expect(g.features[0].properties.readings).toEqual([{ layerId: 'pair-a:gunw-coherence', value: 0.21, units: '1' }])
    expect(g.features[0].properties.explanations[0].standing).toBe('Partly fits')
  })
  it('escapes text in the printable page and labels the hypotheses', () => {
    const h = toHtml(r)
    expect(h).toContain('T &lt;x&gt;')
    expect(h).toContain('Hypothesis')
    expect(h).not.toContain('<x>')
    expect(h).toContain('Context, not counted')
    expect(h).not.toContain('withheld')
  })
  it('says when the observability figures come from the withdrawn method', () => {
    const h = toHtml({ ...r, observability: { ...r.observability!, methodVersion: 1, current: false } })
    expect(h).toContain('method version 1')
    expect(h).toContain('withheld until the corrected run')
  })
  it('carries no script unless it is the saved file, so the print button survives the offline policy', () => {
    expect(toHtml(r)).not.toMatch(/onclick|<script/i)
    expect(toHtml(r)).toContain('<button id="print">')
    expect(toHtml(r, true)).toContain('onclick="print()"')
  })
  it('names the hemisphere from the sign of the coordinates', () => {
    expect(toHtml(r)).toContain('28.10000°N, 85.30000°E')
    expect(toHtml({ ...r, point: { lng: -70.5, lat: -33.4 } })).toContain('33.40000°S, 70.50000°W')
  })
})
