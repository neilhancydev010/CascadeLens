import type { Layer } from '../types/manifest'
import { isUsable } from './manifest'

// One evidence class per result, used the same way on maps, panels, charts and reports.
export type EvidenceClass = 'observed' | 'derived' | 'forecast' | 'hypothesis' | 'reference' | 'simulation' | 'unknown'

export const EVIDENCE: Record<EvidenceClass, { label: string; meaning: string }> = {
  observed: { label: 'Observed', meaning: 'Read straight from a real satellite measurement file.' },
  derived: { label: 'Derived', meaning: 'Calculated by CascadeLens from real measurements. The method is listed with it.' },
  forecast: { label: 'Forecast', meaning: 'A modelled future condition. It is not an observation.' },
  hypothesis: { label: 'Hypothesis', meaning: 'A possible explanation, with the evidence for and against it.' },
  reference: { label: 'Reference', meaning: 'From another published source, such as UNOSAT or OpenStreetMap. Not a NISAR result.' },
  simulation: { label: 'Scenario', meaning: 'A what-if illustration. Nothing like this has been observed.' },
  unknown: { label: 'Unknown', meaning: 'Not enough data to say anything here. Missing data is not the same as safe.' },
}

export function evidenceOf(l: Layer): EvidenceClass {
  if (!isUsable(l)) return 'unknown'
  if (/scenario|simulat/i.test(`${l.productType} ${l.measurementType} ${l.id}`)) return 'simulation'
  if (l.measurementClass === 'measurement') return 'observed'
  if (l.measurementClass === 'derived') return 'derived'
  return 'reference'
}
