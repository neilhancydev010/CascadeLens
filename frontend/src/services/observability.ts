import type { Layer, Manifest } from '../types/manifest'

// Mirrors processing/src/cascade_lens/observability.py. Reasons stay separate; classes are decided per task.
export const FLAG = {
  outside: 1, noData: 2, layover: 4, shadow: 8, lowCoherence: 16, noUnwrapped: 32, lowBaseline: 64,
  productMasked: 128, geometryNotAssessed: 256, baselineNoData: 512,
} as const
export type Task = 'disturbance' | 'movement'

// Version 2 applies the radar product's own quality mask. Figures from version 1 are withheld, never shown as current.
export const OBSERVABILITY_METHOD = 2
export const observabilityCurrent = (m: Manifest | undefined) => (m?.observability?.methodVersion ?? 1) >= OBSERVABILITY_METHOD

// The radar frames the observability block assessed, such as [74, 75], and how to say where the rest lies
export const framesChecked = (m: Manifest | undefined): number[] => m?.observability?.frames?.map((f) => f.frame) ?? (m?.observability ? [m.observability.frame] : [])
export function beyondFrames(m: Manifest | undefined): string {
  const f = framesChecked(m)
  return f.length > 1
    ? `beyond the radar frames checked (${f.slice(0, -1).join(', ')} and ${f[f.length - 1]}), where no frame of this pair was assessed`
    : 'beyond this radar frame, in the neighbouring frame, which is not checked yet'
}
export const STALE_NOTE = 'These figures came from an earlier calculation that did not apply the radar product’s own quality mask. They are withheld until the corrected run.'

const REASON: [number, string][] = [
  [FLAG.outside, 'Outside the radar frames checked here. Another frame may cover it, but it is not assessed.'],
  [FLAG.noData, 'Inside the frame, but the product holds no value here.'],
  [FLAG.productMasked, 'The radar product’s own quality mask flags this spot (water, an invalid subswath or an image anomaly), so its values are not used.'],
  [FLAG.geometryNotAssessed, 'Terrain geometry could not be checked here (elevation or viewing angle missing), so this spot is not assessed.'],
  [FLAG.layover, 'Layover: the slope faces the radar more steeply than its viewing angle, so echoes from different heights pile up.'],
  [FLAG.shadow, 'Radar shadow: the slope faces away too steeply for the radar to reach it.'],
  [FLAG.lowCoherence, 'Low coherence in this pair (below 0.3): the signal changed or is noisy.'],
  [FLAG.noUnwrapped, 'No reliably unwrapped phase here, so no movement value.'],
  [FLAG.lowBaseline, 'Already incoherent before the event (baseline pair below 0.3), so a drop cannot be told from noise.'],
  [FLAG.baselineNoData, 'The pair before the event holds no valid value here, so a change cannot be judged.'],
]

export const CLASS_LABEL: Record<number, string> = {
  1: 'Usable', 2: 'Seen, but not reliable', 3: 'Hidden by terrain', 4: 'No valid data in the product', 5: 'Outside the frame checked', 6: 'Not assessed',
}

export function reasons(flags: number): string[] {
  return REASON.filter(([bit]) => (flags & bit) !== 0).map(([, text]) => text)
}

export function classify(flags: number, task: Task): number {
  if (flags & FLAG.outside) return 5
  if (flags & (FLAG.noData | FLAG.productMasked)) return 4
  if (flags & (FLAG.layover | FLAG.shadow)) return 3
  if (flags & (FLAG.geometryNotAssessed | (task === 'disturbance' ? FLAG.baselineNoData : 0))) return 6
  const poor = task === 'disturbance' ? flags & FLAG.lowBaseline : flags & (FLAG.lowCoherence | FLAG.noUnwrapped)
  return poor ? 2 : 1
}

export const isObservability = (l: Layer) => l.measurementType.startsWith('observability-')

// One viewing direction: the observability layers that share one reason-flag raster. Flags from one view must never be read
// through another view's layers. Views keep manifest order, so the main view (Track 48) comes first.
export interface ObsView { key: string; label: string; layers: Layer[] }

export function obsViews(layers: Layer[]): ObsView[] {
  const by = new Map<string, Layer[]>()
  for (const l of layers.filter(isObservability)) {
    const key = l.sources[0]?.sampling ?? l.id
    by.set(key, [...(by.get(key) ?? []), l])
  }
  return [...by.entries()].map(([key, ls]) => {
    const l = ls[0]
    const pass = l.orbitDirection ? `, ${l.orbitDirection.toLowerCase()}` : ''
    return { key, layers: ls, label: `Track ${l.track ?? '?'}${pass}, frame${l.frames.length > 1 ? 's' : ''} ${l.frames.join(' and ')}` }
  })
}
export const taskOf = (l: Layer) => l.measurementType.replace('observability-', '') as Task

// The class label as the layer's legend gives it, falling back to the shared labels for codes an older legend lacks.
export const classLabel = (l: Layer, code: number) => l.legend?.keys?.[code - 1]?.label ?? CLASS_LABEL[code] ?? ''

export function classInfo(m: Manifest | undefined, task: Task, code: number) {
  return m?.observability?.classes[task]?.find((c) => c.code === code)
}
