import { describe, expect, it } from 'vitest'
import { explain, inGeometry, viewSummary, type Clues, type ViewClues } from './hypotheses'
import { FLAG } from './observability'

const view: ViewClues = { label: '', flags: 0, hasBaseline: true, coherence: 0.7, cohPair: '2026-08-16 to 2026-08-28', offset: 0.1, offsetUsual: 0.5, snr: 20, snrMedian: 11, control: null }
type Flat = Partial<ViewClues> & Partial<Omit<Clues, 'views'>>
// One viewing direction, as for Tsho Rolpa: the wording carries no track label
const one = (x: Flat = {}): Clues => {
  const { elevation = 1500, slopeDeg = 10, inside = { mapped: [], water: [] }, ...v } = x
  return { views: [{ ...view, ...v }], elevation, slopeDeg, inside }
}
const base = one()
const T48 = 'Track 48 (descending)', T98 = 'Track 98 (ascending)'
const two = (a: Partial<ViewClues>, b: Partial<ViewClues>, rest: Partial<Omit<Clues, 'views'>> = {}): Clues =>
  ({ views: [{ ...view, label: T48, ...a }, { ...view, label: T98, cohPair: '2026-08-19 to 2026-08-31', ...b }], elevation: 1500, slopeDeg: 10, inside: { mapped: [], water: [] }, ...rest })
const MAPPED = { mapped: ['UNOSAT mudflow/rockflow extent'], water: [] }

describe('hypotheses', () => {
  it('ranks "nothing changed" first where coherence stayed high and nothing is mapped', () => {
    expect(explain(base)[0].id).toBe('nochange')
  })

  it('ranks disturbance first for a coherence drop inside a mapped extent, counting only point values and mapping', () => {
    const h = explain(one({ coherence: 0.12, slopeDeg: 34, inside: MAPPED, control: { inside: 0.28, outside: 0.52, pair: 'x' } }))
    expect(h[0].id).toBe('disturbance')
    expect(h[0].standing).toBe('Fits the checks')
    expect(h[0].for).toHaveLength(2)
    expect(h[0].context.join(' ')).toMatch(/Steep ground.*not show that anything moved/)
    expect(h[0].context.join(' ')).toContain('area-wide figure')
    expect(h.find((x) => x.id === 'nochange')!.standing).toBe('Little support')
  })

  it('cannot rise without a radar value at the spot, however suggestive the place', () => {
    const h = explain(one({ coherence: null, offset: null, offsetUsual: null, slopeDeg: 40, inside: MAPPED, control: { inside: 0.28, outside: 0.52, pair: 'x' } }))
    const d = h.find((x) => x.id === 'disturbance')!
    expect(d.standing).toBe('Cannot judge here')
    expect(d.missing[0]).toContain('A valid radar value at this spot')
    expect(h.find((x) => x.id === 'nochange')!.standing).toBe('Cannot judge here')
  })

  it('does not count the absence of mapping as evidence against a change', () => {
    const d = explain(one({ coherence: 0.1 })).find((x) => x.id === 'disturbance')!
    expect(d.against).toHaveLength(0)
    expect(d.context.join(' ')).toContain('mapping is incomplete')
  })

  it('does not credit a drop where the ground was already noisy before', () => {
    const h = explain(one({ flags: FLAG.lowBaseline, coherence: 0.1 }))
    const d = h.find((x) => x.id === 'disturbance')!
    expect(d.for.join(' ')).not.toContain('stable before')
    expect(d.missing.join(' ')).toContain('cannot be told apart')
    expect(h.find((x) => x.id === 'seasonal')!.for.length).toBeGreaterThan(0)
  })

  it('does not credit a drop when the pair before the event holds no value', () => {
    const d = explain(one({ flags: FLAG.baselineNoData, coherence: 0.1 })).find((x) => x.id === 'disturbance')!
    expect(d.for.join(' ')).not.toContain('coherent before')
    expect(d.missing.join(' ')).toContain('pair before the event')
  })

  it('puts the terrain artefact first under layover, and does not count a drop the terrain may cause', () => {
    const h = explain(one({ flags: FLAG.layover, coherence: 0.2 }))
    expect(h[0].id).toBe('artefact')
    const d = h.find((x) => x.id === 'disturbance')!
    expect(d.for.join(' ')).not.toContain('Coherence fell')
    expect(d.missing.join(' ')).toContain('may be a viewing effect and is not counted')
  })

  it('refuses to explain where the radar did not look', () => {
    for (const flags of [null, FLAG.outside, FLAG.noData, FLAG.productMasked]) {
      const h = explain(one({ flags }))
      expect(h).toHaveLength(1)
      expect(h[0].standing).toBe('Cannot judge here')
    }
  })

  it('never states a probability', () => {
    const text = JSON.stringify([explain(one({ coherence: 0.1, inside: { mapped: ['x'], water: ['lake'] } })), explain(two({ coherence: 0.1 }, { coherence: 0.05 }, { inside: { mapped: ['x'], water: ['lake'] } }))])
    expect(text).not.toMatch(/%|probab|likel/i)
  })

  it('keeps one direction\'s wording free of track labels, and gives no direction summary', () => {
    const h = explain(one({ coherence: 0.12, inside: MAPPED }))
    expect(JSON.stringify(h)).not.toContain('Track ')
    expect(viewSummary(one())).toEqual([])
  })

  it('reads the opposite direction where the first one cannot see, and labels each check with its track', () => {
    const c = two({ flags: FLAG.productMasked, coherence: null }, { coherence: 0.09 }, { inside: MAPPED })
    const h = explain(c)
    expect(h.map((x) => x.id)).not.toContain('unseen')
    const d = h.find((x) => x.id === 'disturbance')!
    expect(d.for).toEqual([`${T98}: Coherence fell to 0.09 in the 2026-08-19 to 2026-08-31 pair while the ground was coherent before the event.`, 'Inside an independently mapped area: UNOSAT mudflow/rockflow extent.'])
    expect(d.standing).toBe('Fits the checks')
    expect(JSON.stringify(h)).not.toContain(`${T48}: Coherence`) // a direction that cannot see the spot adds nothing
    expect(viewSummary(c)).toEqual([
      `${T48}: cannot judge this spot. The radar product’s own quality mask flags this spot (water, an invalid subswath or an image anomaly), so its values cannot be used.`,
      `${T98}: coherence 0.09 in the 2026-08-19 to 2026-08-31 pair and a pixel offset.`,
    ])
  })

  it('counts each direction\'s radar check once, and independent mapping once', () => {
    const d = explain(two({ coherence: 0.12 }, { coherence: 0.08 }, { inside: MAPPED })).find((x) => x.id === 'disturbance')!
    expect(d.for).toHaveLength(3)
    expect(d.for.filter((t) => t.startsWith('Inside an independently mapped area'))).toHaveLength(1)
    const mixed = explain(two({ coherence: 0.7 }, { coherence: 0.1 })).find((x) => x.id === 'disturbance')!
    expect(mixed.for).toEqual([`${T98}: Coherence fell to 0.10 in the 2026-08-19 to 2026-08-31 pair while the ground was coherent before the event.`])
    expect(mixed.against).toEqual([`${T48}: Coherence stayed high (0.70): the radar echo barely changed.`])
    expect(mixed.standing).toBe('Little support')
  })

  it('does not call a change a terrain artefact when the other direction is not hidden', () => {
    const oneSide = explain(two({ flags: FLAG.layover, coherence: 0.2 }, { coherence: 0.1 })).find((x) => x.id === 'artefact')!
    expect(oneSide.standing).not.toBe('Fits the checks')
    expect(oneSide.for).toEqual([`${T48}: Layover here: echoes from different heights land on the same pixel.`])
    expect(oneSide.against).toEqual([`${T98}: Not hidden by terrain from this viewing angle.`])
    expect(oneSide.missing.join(' ')).not.toContain('opposite direction')
    const both = explain(two({ flags: FLAG.layover, coherence: 0.2 }, { flags: FLAG.shadow, coherence: 0.2 }))
    expect(both[0].id).toBe('artefact')
    expect(both[0].standing).toBe('Fits the checks')
  })

  it('refuses to explain only when no direction can see the spot, and says why for each', () => {
    const h = explain(two({ flags: FLAG.productMasked }, { flags: FLAG.outside }))
    expect(h).toHaveLength(1)
    expect(h[0].standing).toBe('Cannot judge here')
    expect(h[0].title).toBe('No NISAR explanation from the directions checked')
    expect(h[0].for[0]).toMatch(/^Track 48 \(descending\): The radar product’s own quality mask/)
    expect(h[0].for[1]).toMatch(/^Track 98 \(ascending\): This spot is outside the radar frames/)
  })

  it('uses each direction\'s own area-wide control figure as context, never as a count', () => {
    const d = explain(two({ coherence: 0.12, control: { inside: 0.19, outside: 0.5, pair: 'A' } }, { coherence: 0.09, control: { inside: 0.13, outside: 0.49, pair: 'B' } }, { inside: MAPPED }))
      .find((x) => x.id === 'disturbance')!
    expect(d.context.filter((t) => t.includes('area-wide figure'))).toEqual([
      `${T48}: Across the whole mapped mudflow, median coherence was 0.19 against 0.50 on ground nearby in the same pair (A). That is an area-wide figure, not a reading at this spot.`,
      `${T98}: Across the whole mapped mudflow, median coherence was 0.13 against 0.49 on ground nearby in the same pair (B). That is an area-wide figure, not a reading at this spot.`,
    ])
    expect(d.for).toHaveLength(3)
  })

  it('tests points against polygons with holes', () => {
    const g = { type: 'Polygon', coordinates: [[[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]], [[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]]] }
    expect(inGeometry([3, 3], g)).toBe(true)
    expect(inGeometry([1.5, 1.5], g)).toBe(false)
    expect(inGeometry([5, 5], g)).toBe(false)
  })
})
