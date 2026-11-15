import type { Layer } from '../types/manifest'
import { classify, FLAG, type Task } from './observability'
import { isUsable } from './manifest'

// Evidence gap → next observation (brief §7.3). A fixed rule table, with no model or text generation: every step names the
// rule that produced it, and says whether the evidence it points to is already in CascadeLens, is only listed in the
// catalogue, was not found, or needs a person to collect it. A step never claims that better data exists unless the
// shipped manifest actually holds it.

export type Availability = 'available' | 'catalogued' | 'not-found' | 'human'

export const AVAILABILITY_TEXT: Record<Availability, string> = {
  available: 'Already in CascadeLens',
  catalogued: 'Listed in the catalogue, not downloaded',
  'not-found': 'Not found in the data here',
  human: 'Needs a person to collect it',
}

export interface NextStep { rule: string; gap: string; step: string; availability: Availability; detail: string }

// One viewing direction at one spot: its track and its reason flags (null when the spot lies outside everything it assessed).
export interface ViewFlags { label: string; track: number | null; flags: number | null }

const usableFor = (v: ViewFlags, task: Task) => v.flags !== null && classify(v.flags, task) === 1

function otherView(views: ViewFlags[], self: ViewFlags, task: Task, rule: string, gap: string, step: string): NextStep {
  const others = views.filter((v) => v !== self)
  const good = others.find((v) => usableFor(v, task))
  if (good) return { rule, gap, step, availability: 'available', detail: `${good.label} is processed here and is usable for this question at this spot. Read its answer above.` }
  if (others.length) return { rule, gap, step, availability: 'not-found', detail: `The other processed direction (${others.map((o) => o.label).join(', ')}) cannot answer this question here either. No further processed observation covers this spot.` }
  return { rule, gap, step, availability: 'not-found', detail: 'No other processed observation covers this spot. A neighbouring frame or a later pass may exist in the ASF catalogue, but none has been found or processed for this spot.' }
}

function sameTrack(layers: Layer[], track: number | null, test: (l: Layer) => boolean) {
  return layers.filter((l) => isUsable(l) && test(l) && (track === null || l.track === track))
}

function catalogued(layers: Layer[], track: number | null, type: string) {
  return layers.filter((l) => l.status === 'catalogued' && l.productType === type && (track === null || l.track === track))
}

const HUMAN: NextStep = {
  rule: 'R-INDEPENDENT', gap: 'Radar cannot settle this spot', step: 'Check independent imagery or a field report',
  availability: 'human', detail: 'An optical image taken after the event (such as Sentinel-2) or a person on the ground. Add what they find to the field-check list; it stays separate from the satellite record.',
}

// The steps for one viewing direction and one question. Usable spots get only the timing caveat, when it applies.
export function nextSteps(task: Task, self: ViewFlags, views: ViewFlags[], layers: Layer[]): NextStep[] {
  const steps: NextStep[] = []
  const f = self.flags
  if (f === null || f & FLAG.outside) {
    steps.push(otherView(views, self, task, 'R-OUTSIDE', 'Outside the frames assessed', 'Look for a neighbouring frame or another pass'))
    return [...steps, HUMAN]
  }
  if (f & (FLAG.noData | FLAG.productMasked)) {
    steps.push(otherView(views, self, task, 'R-MASK', f & FLAG.productMasked ? 'The product’s own mask excludes this spot' : 'No value in the product here', 'Leave these values out and use another suitable observation'))
    const loaded = sameTrack(layers, self.track, (l) => l.productType === 'GCOV' || l.measurementType === 'gcov-change')
    const gcov = catalogued(layers, self.track, 'GCOV')
    const step = 'A backscatter (GCOV) image of the same pass could show surface change'
    if (task === 'disturbance' && loaded.length) steps.push({ rule: 'R-MASK-GCOV', gap: 'No interferometric value here', step, availability: 'available', detail: `Loaded for this track: ${loaded.map((l) => `${l.name}, ${l.acquisition.secondary ? `${l.acquisition.reference} to ${l.acquisition.secondary}` : l.acquisition.reference}`).join('; ')}. Under Radar evidence, Snapshots. Backscatter has its own gaps, so check that it holds a value at this spot.` })
    else if (task === 'disturbance' && gcov.length) steps.push({ rule: 'R-MASK-GCOV', gap: 'No interferometric value here', step, availability: 'catalogued', detail: `${gcov.map((l) => l.name).join('; ')}: in the catalogue but not downloaded, so it has not been checked for this spot.` })
  }
  if (f & (FLAG.layover | FLAG.shadow)) {
    steps.push(otherView(views, self, task, 'R-TERRAIN', f & FLAG.shadow ? 'Radar shadow' : 'Layover', 'Check another viewing geometry'))
  }
  if (f & FLAG.geometryNotAssessed) {
    steps.push({ rule: 'R-GEOMETRY', gap: 'Terrain geometry not assessed', step: 'Supply elevation and viewing angles for this spot', availability: 'not-found', detail: 'The elevation model or the product’s viewing angles are missing here, so layover and shadow cannot be ruled out. Nothing in this build fills the gap.' })
  }
  if (task === 'movement' && f & (FLAG.lowCoherence | FLAG.noUnwrapped)) {
    const goff = sameTrack(layers, self.track, (l) => l.measurementType === 'goff-range' || l.measurementType === 'goff-azimuth')
    steps.push(goff.length
      ? { rule: 'R-PHASE', gap: f & FLAG.noUnwrapped ? 'No reliably unwrapped phase' : 'Low coherence', step: 'Do not infer movement from phase here. Pixel offsets (GOFF) are the other measurement', availability: 'available', detail: `${goff.map((l) => l.name).join(' and ')} for the same pair are loaded. They are coarser, measure a different thing, and are not converted to movement in CascadeLens.` }
      : { rule: 'R-PHASE', gap: 'No usable phase', step: 'Do not infer movement here; a displacement observation is needed', availability: 'not-found', detail: 'No pixel-offset product for this pass is loaded.' })
  }
  if (task === 'disturbance' && f & (FLAG.lowBaseline | FLAG.baselineNoData)) {
    const series = sameTrack(layers, self.track, (l) => (l.timeSteps?.length ?? 0) > 1 && l.measurementType === 'gunw-coherence')
    steps.push(series.length
      ? { rule: 'R-BASELINE', gap: f & FLAG.baselineNoData ? 'No valid value before the event' : 'Already incoherent before the event', step: 'Compare this spot across other pairs of the same track', availability: 'available', detail: `${series.map((l) => l.name).join('; ')} holds ${series[0].timeSteps!.length} pairs. Read this spot in each before trusting any single before-and-after contrast.` }
      : { rule: 'R-BASELINE', gap: 'No usable before-event pair', step: 'Find another compatible before-event pair', availability: 'not-found', detail: 'No other pair of this track is loaded.' })
  }
  if (classify(f, task) === 1) {
    if (task === 'disturbance') steps.push({ rule: 'R-TIMING', gap: 'The pair spans the event', step: 'Read additional compatible dates', availability: sameTrack(layers, self.track, (l) => (l.timeSteps?.length ?? 0) > 1).length ? 'available' : 'not-found', detail: 'A pair that spans the event shows that the surface changed somewhere between its two dates. It cannot date the change or establish its cause.' })
    return steps
  }
  if (classify(f, task) === 2 && !steps.length) steps.push(otherView(views, self, task, 'R-QUALITY', 'Seen, but not reliable', 'Look for a clearer observation'))
  return [...steps, HUMAN]
}
