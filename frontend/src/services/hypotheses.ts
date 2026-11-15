import type { Layer, Manifest } from '../types/manifest'
import { assetUrl, isUsable } from './manifest'
import { samplePoint } from './sampler'
import { FLAG, obsViews } from './observability'

// "What could explain this?" A rule-based screen of a few explanations at one clicked spot.
// It counts which checks agree and lists what is missing. It is never a probability or a verdict.

// What one viewing direction (radar track) shows at the spot. Each direction is read from its own flags and its own pair.
export interface ViewClues {
  label: string // 'Track 98 (ascending)'; empty when the case has one direction
  flags: number | null | undefined // observability reason flags; null = outside the assessed area, undefined = no observability layer
  hasBaseline: boolean
  coherence: number | null
  cohPair: string | null
  offset: number | null // largest departure of the pixel offsets from the scene median, metres
  offsetUsual: number | null // the scene's usual spread (p2 to p98 half-width), metres
  snr: number | null
  snrMedian: number | null
  control: { inside: number; outside: number; pair: string } | null
}

export interface Clues {
  views: ViewClues[] // the main direction first
  elevation: number | null
  slopeDeg: number | null
  inside: { mapped: string[]; water: string[] }
}

// The standing describes how the counted checks fall. It is a count, not a probability or a verdict.
export type Standing = 'Fits the checks' | 'Partly fits' | 'Little support' | 'Cannot judge here'

export interface Hypothesis {
  id: string
  title: string
  standing: Standing
  for: string[] // counted: a radar value at this spot (one per direction), or independent mapping of this spot
  against: string[] // counted
  context: string[] // not counted: what the place is like (slope, height, area-wide figures), which cannot show that anything happened here
  missing: string[]
}

export const COH_LOW = 0.3
export const COH_HIGH = 0.6
export const STEEP_DEG = 25
export const HIGH_ICE_M = 4800

const f2 = (v: number) => v.toFixed(2)
const NEEDS_VALUE = 'A valid radar value at this spot (coherence or pixel offset). Without one, the radar cannot speak for or against this.'

function standing(forN: number, againstN: number): Standing {
  const s = forN - againstN
  return s >= 2 ? 'Fits the checks' : s >= 1 ? 'Partly fits' : 'Little support'
}

// One direction's reading of its own flags and values
function read(v: ViewClues) {
  const fl = v.flags ?? 0
  const unseen = v.flags === null || Boolean(fl & (FLAG.outside | FLAG.noData | FLAG.productMasked))
  const why = v.flags === null ? 'This spot lies outside the area the radar check covers.'
    : fl & FLAG.outside ? 'This spot is outside the radar frames checked here. Another frame may cover it, but it is not assessed.'
      : fl & FLAG.productMasked ? 'The radar product’s own quality mask flags this spot (water, an invalid subswath or an image anomaly), so its values cannot be used.'
        : 'The radar product holds no value at this spot.'
  const coh = v.coherence
  const offsetKnown = v.offset !== null && v.offsetUsual !== null
  return {
    v, fl, unseen, why, coh, offsetKnown,
    hidden: Boolean(fl & (FLAG.layover | FLAG.shadow)),
    geometryUnknown: Boolean(fl & FLAG.geometryNotAssessed),
    lowBase: Boolean(fl & FLAG.lowBaseline),
    baseKnown: v.hasBaseline && v.flags !== undefined && !(fl & FLAG.baselineNoData),
    dropped: coh !== null && coh < COH_LOW,
    stable: coh !== null && coh >= COH_HIGH,
    shifted: offsetKnown && v.offset! > v.offsetUsual! && (v.snr === null || v.snrMedian === null || v.snr >= v.snrMedian),
    measured: coh !== null || offsetKnown,
  }
}

// What each direction could do at this spot, for the panel and the report. Empty when the case has one direction.
export function viewSummary(c: Clues): string[] {
  if (c.views.length < 2) return []
  return c.views.map((v) => {
    const r = read(v)
    if (r.unseen) return `${v.label}: cannot judge this spot. ${r.why}`
    const parts = [r.coh !== null ? `coherence ${f2(r.coh)} in the ${v.cohPair} pair` : 'no coherence value', r.offsetKnown ? 'a pixel offset' : null].filter(Boolean)
    return `${v.label}: ${parts.join(' and ')}${r.hidden ? '; hidden by terrain from this side' : ''}.`
  })
}

export function explain(c: Clues): Hypothesis[] {
  const many = c.views.length > 1
  const tag = (v: ViewClues, t: string) => (many ? `${v.label}: ${t}` : t)
  const all = c.views.map(read)
  const seen = all.filter((r) => !r.unseen)
  const field = 'A field report or a cloud-free before-and-after optical image of this spot.'

  if (!seen.length) {
    return [{ id: 'unseen', title: many ? 'No NISAR explanation from the directions checked' : 'No NISAR explanation from the frame checked', standing: 'Cannot judge here',
      for: all.map((r) => tag(r.v, r.why)), against: [], context: [],
      missing: [many ? 'A radar pair that covers this spot with valid data.' : 'A radar pair that covers this spot with valid data (the next frame along the track, or the other track in the download list).', field] }]
  }

  const measured = seen.some((r) => r.measured)
  const steep = c.slopeDeg !== null && c.slopeDeg >= STEEP_DEG
  const out: Hypothesis[] = []
  const judge = (f: string[], a: string[], needs: boolean): Standing => (needs ? standing(f.length, a.length) : 'Cannot judge here')

  // 1. Real surface disturbance
  {
    const f: string[] = [], a: string[] = [], x: string[] = [], m: string[] = []
    for (const r of seen) {
      const { v } = r
      // Where terrain hides the slope from this side, a drop may be a viewing effect: the observability check cannot judge change there
      if (r.dropped && r.hidden) m.push(tag(v, 'This side is hidden by terrain here (layover or shadow), so its coherence drop may be a viewing effect and is not counted.'))
      else if (r.dropped && r.baseKnown && !r.lowBase) f.push(tag(v, `Coherence fell to ${f2(r.coh!)} in the ${v.cohPair} pair while the ground was coherent before the event.`))
      if (r.dropped && !r.hidden && r.lowBase) m.push(tag(v, 'The spot was already noisy before the event, so this drop cannot be told apart from normal noise.'))
      if (r.dropped && !r.hidden && !r.baseKnown) m.push(tag(v, 'A valid value from the pair before the event, to show the spot was coherent beforehand.'))
      if (r.stable) a.push(tag(v, `Coherence stayed high (${f2(r.coh!)}): the radar echo barely changed.`))
      if (r.shifted) f.push(tag(v, `The image features moved ${f2(v.offset!)} m from the scene's usual shift, more than its normal spread (${f2(v.offsetUsual!)} m), with a clear match.`))
      if (v.control && c.inside.mapped.length) x.push(tag(v, `Across the whole mapped mudflow, median coherence was ${f2(v.control.inside)} against ${f2(v.control.outside)} on ground nearby in the same pair (${v.control.pair}). That is an area-wide figure, not a reading at this spot.`))
      if (r.coh === null) m.push(tag(v, 'Coherence for the event pair at this spot.'))
      if (!v.hasBaseline) m.push(tag(v, 'A radar pair from before the event, to show the spot was stable beforehand.'))
    }
    if (c.inside.mapped.length) f.push(`Inside an independently mapped area: ${c.inside.mapped.join(', ')}.`)
    else x.unshift('Not inside any independently mapped change area. That is not evidence that nothing changed: mapping is incomplete.')
    if (steep) x.push(`Steep ground (${Math.round(c.slopeDeg!)}°). Slope makes failure more likely in general; it does not show that anything moved here.`)
    if (!measured) m.unshift(NEEDS_VALUE)
    m.push(field)
    out.push({ id: 'disturbance', title: 'The ground surface was disturbed (debris flow, landslide, erosion or new deposits)', standing: judge(f, a, measured), for: f, against: a, context: x, missing: m })
  }

  // 2. Ordinary seasonal or natural change
  {
    const f: string[] = [], a: string[] = [], x: string[] = [], m: string[] = []
    for (const r of seen) {
      const { v } = r
      if (r.lowBase) f.push(tag(v, 'The spot was already incoherent in the pair before the event, as vegetation, snow or wet soil often make it.'))
      else if (r.baseKnown) a.push(tag(v, 'The spot was coherent in the pair before the event, so it is not always noisy.'))
      if (r.stable) a.push(tag(v, 'Coherence stayed high, so there was little change of any kind.'))
      if (v.control && r.dropped) x.push(tag(v, `Ground near the mudflow kept its coherence in the same pair (median ${f2(v.control.outside)}), so the season did not lower coherence everywhere. That is an area-wide figure, not a reading at this spot.`))
    }
    if (c.elevation !== null && c.elevation >= HIGH_ICE_M) x.unshift(`High ground (${Math.round(c.elevation)} m), where snow and ice often change between passes.`)
    const judged = measured || seen.some((r) => r.baseKnown)
    if (!judged) m.push(NEEDS_VALUE)
    m.push('The same pair of dates from a previous year, to see the normal seasonal drop.')
    out.push({ id: 'seasonal', title: 'Ordinary seasonal change (vegetation, snow, ice or wet soil)', standing: judge(f, a, judged), for: f, against: a, context: x, missing: m })
  }

  // 3. Water surface
  const veryLow = seen.filter((r) => r.coh !== null && r.coh < 0.15)
  if (c.inside.water.length || veryLow.length) {
    const f: string[] = [], x: string[] = []
    if (c.inside.water.length) f.push(`Inside a mapped water body: ${c.inside.water.join(', ')}.`)
    for (const r of veryLow) f.push(tag(r.v, `Very low coherence (${f2(r.coh!)}), typical of moving water.`))
    if (!c.inside.water.length) x.push('Not inside any mapped lake. Rivers and new ponds may be unmapped.')
    out.push({ id: 'water', title: 'Open water (river channel or lake), which never stays coherent', standing: standing(f.length, 0), for: f, against: [], context: x,
      missing: ['A water mask from the same dates (for example a NISAR backscatter snapshot).'] })
  }

  // 4. Viewing artefact: terrain hides a slope from one side only, so a direction that is not hidden counts against it
  {
    const f: string[] = [], a: string[] = [], m: string[] = []
    for (const r of seen) {
      const { v, fl } = r
      if (fl & FLAG.layover) f.push(tag(v, 'Layover here: echoes from different heights land on the same pixel.'))
      if (fl & FLAG.shadow) f.push(tag(v, 'Radar shadow here: the radar cannot reach this slope.'))
      if (fl & FLAG.noUnwrapped) f.push(tag(v, 'No reliably unwrapped phase at this spot, so the processing dropped it.'))
      if (!r.hidden && !r.geometryUnknown && v.flags !== undefined) a.push(tag(v, 'Not hidden by terrain from this viewing angle.'))
      if (r.geometryUnknown) m.push(tag(v, 'Elevation and viewing angles at this spot, to check for layover and shadow.'))
    }
    if (!many) m.push('The same spot seen from the opposite direction (an ascending pass).')
    const allHidden = seen.every((r) => r.hidden)
    const unknown = seen.every((r) => r.geometryUnknown)
    out.push({ id: 'artefact', title: 'A radar viewing artefact, not a real change', standing: allHidden ? 'Fits the checks' : unknown && !f.length ? 'Cannot judge here' : standing(f.length, a.length),
      for: f, against: a, context: [], missing: m })
  }

  // 5. No change
  {
    const f: string[] = [], a: string[] = []
    for (const r of seen) {
      const { v } = r
      if (r.stable) f.push(tag(v, `Coherence stayed high (${f2(r.coh!)}).`))
      if (r.dropped) a.push(tag(v, `Coherence dropped to ${f2(r.coh!)}.`))
      if (r.offsetKnown && !r.shifted) f.push(tag(v, 'Image features did not shift beyond the scene\'s normal spread.'))
      if (r.shifted) a.push(tag(v, 'Image features shifted more than the scene\'s normal spread.'))
    }
    if (c.inside.mapped.length) a.push(`Inside an independently mapped area: ${c.inside.mapped.join(', ')}.`)
    out.push({ id: 'nochange', title: 'Nothing changed here', standing: judge(f, a, measured), for: f, against: a, context: [], missing: measured ? [field] : [NEEDS_VALUE, field] })
  }

  const order: Standing[] = ['Fits the checks', 'Partly fits', 'Little support', 'Cannot judge here']
  return out.sort((x, y) => order.indexOf(x.standing) - order.indexOf(y.standing) || (y.for.length - y.against.length) - (x.for.length - x.against.length))
}

// ---- gathering the clues at one point ----

type Ring = number[][]
type Geom = { type: string; coordinates: unknown }
const shapes = new Map<string, Promise<Geom[]>>()

function inRing(p: [number, number], ring: Ring) {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j]
    if ((yi > p[1]) !== (yj > p[1]) && p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

export function inGeometry(p: [number, number], g: Geom): boolean {
  const poly = (rings: Ring[]) => inRing(p, rings[0]) && !rings.slice(1).some((h) => inRing(p, h))
  if (g.type === 'Polygon') return poly(g.coordinates as Ring[])
  if (g.type === 'MultiPolygon') return (g.coordinates as Ring[][]).some(poly)
  return false
}

async function inside(layer: Layer, p: [number, number]) {
  const v = layer.vector!
  const [w, s, e, n] = v.bounds
  if (p[0] < w || p[0] > e || p[1] < s || p[1] > n) return false
  if (!shapes.has(v.url)) shapes.set(v.url, fetch(assetUrl(v.url)).then((r) => r.json()).then((fc) => (fc.features ?? []).map((x: { geometry: Geom }) => x.geometry).filter(Boolean)).catch(() => []))
  return (await shapes.get(v.url)!).some((g) => inGeometry(p, g))
}

const valid = async (l: Layer | undefined, p: [number, number]) => {
  if (!l) return null
  const r = await samplePoint(l, p[0], p[1])
  return r.state === 'valid' && r.value !== undefined ? r.value : null
}

const WATER = /lake|water|river/i
const MAPPED = /extent|detachment|change|damage|affected|landslide/i

// The event-pair coherence and offsets of one track, never the coherence-through-time layers
const eventCoherence = (usable: Layer[], track: number | null | undefined) =>
  usable.find((l) => l.measurementType === 'gunw-coherence' && l.category !== 'preview' && l.groupId && !l.timeSteps && (track == null || l.track === track))

async function viewClues(m: Manifest, usable: Layer[], p: [number, number], flagLayer: Layer | undefined, track: number | null | undefined, label: string): Promise<ViewClues> {
  const coh = eventCoherence(usable, track)
  const sameTrack = (l: Layer) => track == null || l.track === track
  const rng = usable.find((l) => l.measurementType === 'goff-range' && l.groupId === coh?.groupId) ?? usable.find((l) => l.measurementType === 'goff-range' && sameTrack(l))
  const az = usable.find((l) => l.measurementType === 'goff-azimuth' && l.groupId === rng?.groupId)
  const snr = usable.find((l) => l.measurementType === 'goff-snr' && l.groupId === rng?.groupId)
  const [flags, c, r, a, s] = await Promise.all([
    flagLayer ? valid(flagLayer, p) : Promise.resolve(undefined),
    valid(coh, p), valid(rng, p), valid(az, p), valid(snr, p),
  ])
  const dev = (v: number | null, l: Layer | undefined) => (v === null || l?.stats?.median === undefined ? null : Math.abs(v - l.stats.median))
  const spread = (l: Layer | undefined) => { const st = l?.stats as { p2?: number; p98?: number } | undefined; return st?.p2 !== undefined && st?.p98 !== undefined ? (st.p98 - st.p2) / 2 : null }
  const devs = [[dev(r, rng), spread(rng)], [dev(a, az), spread(az)]].filter((x): x is [number, number] => x[0] !== null && x[1] !== null)
  const worst = devs.sort((x, y) => y[0] / y[1] - x[0] / x[1])[0]
  // This direction's own observability block and control series
  const block = [m.observability, ...Object.values(m.observabilityViews ?? {})].find((o) => o && (track == null || o.track === track))
  const series = [m.controlSeries, ...Object.values(m.controlSeriesViews ?? {})].find((x) => x && (track == null || x.track === track))
  const co = series?.pairs.find((x) => coh && x.pair[0] === coh.acquisition.reference && x.pair[1] === coh.acquisition.secondary)
  return {
    label,
    flags,
    hasBaseline: Boolean(block?.baselinePair),
    coherence: c,
    cohPair: coh ? `${coh.acquisition.reference} to ${coh.acquisition.secondary}` : null,
    offset: worst ? worst[0] : null,
    offsetUsual: worst ? worst[1] : null,
    snr: s,
    snrMedian: snr?.stats?.median ?? null,
    control: co ? { inside: co.inside, outside: co.outside, pair: `${co.pair[0]} to ${co.pair[1]}` } : null,
  }
}

export async function gather(m: Manifest, p: [number, number]): Promise<Clues> {
  const usable = m.layers.filter(isUsable)
  const views = obsViews(usable)
  const dem = usable.find((l) => l.measurementType === 'elevation')
  const polys = usable.filter((l) => l.category === 'reference' && l.vector?.type === 'fill' && !/analys|district|scenario|if a /i.test(`${l.id} ${l.name}`))

  const d = 45 // metres either side for the slope
  const dLng = d / (111320 * Math.cos((p[1] * Math.PI) / 180)), dLat = d / 110540
  // One set of clues per viewing direction, each from its own flags; a case without observability layers has one, unflagged
  const name = (l: Layer) => `Track ${l.track ?? '?'}${l.orbitDirection ? ` (${l.orbitDirection.toLowerCase()})` : ''}`
  const plan: [Layer | undefined, number | null | undefined, string][] = views.length
    ? views.map((v) => [v.layers[0], v.layers[0].track, views.length > 1 ? name(v.layers[0]) : ''])
    : [[undefined, eventCoherence(usable, null)?.track ?? null, '']]
  const [vc, z, ze, zw, zn, zs, hits] = await Promise.all([
    Promise.all(plan.map(([fl, track, label]) => viewClues(m, usable, p, fl, track, label))),
    valid(dem, p), valid(dem, [p[0] + dLng, p[1]]), valid(dem, [p[0] - dLng, p[1]]), valid(dem, [p[0], p[1] + dLat]), valid(dem, [p[0], p[1] - dLat]),
    Promise.all(polys.map((l) => inside(l, p))),
  ])
  const slope = [z, ze, zw, zn, zs].every((v) => v !== null) ? (Math.atan(Math.hypot((ze! - zw!) / (2 * d), (zn! - zs!) / (2 * d))) * 180) / Math.PI : null
  const names = polys.filter((_, i) => hits[i]).map((l) => l.name.replace(/\s*\(.*\)$/, ''))
  return {
    views: vc,
    elevation: z,
    slopeDeg: slope,
    inside: { mapped: names.filter((n) => MAPPED.test(n) && !WATER.test(n)), water: names.filter((n) => WATER.test(n)) },
  }
}
