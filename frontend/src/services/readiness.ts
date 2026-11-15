import { assetUrl } from './manifest'

// Written by processing/scripts/prepare_readiness.py: the state each flood and landslide capability has earned from the data
// on disk, with the checks behind it. The app never shows a capability above that state.
export interface ReadinessCheck { id: string; ok: boolean; reason: string }
export interface ReadinessCapability {
  capability: string; name: string; family: 'flood' | 'landslide'; state: string; checks: ReadinessCheck[]
  partial: string[]; next_requirement: string | null; decision: string | null; ceiling: string | null
}
export interface Readiness { generatedAt: string; states: string[]; capabilities: ReadinessCapability[]; datasets: Record<string, { name: string; onDisk: boolean; source?: string }> }

export async function loadReadiness(): Promise<Readiness | null> {
  try {
    const r = await fetch(assetUrl('data/readiness.json'))
    return r.ok ? ((await r.json()) as Readiness) : null
  } catch {
    return null
  }
}

// The missing or unfit inputs, in plain words, for one capability: only the failing checks, at most `n`.
export function blockers(c: ReadinessCapability, n = 3): string[] {
  return c.checks.filter((x) => !x.ok && !RUNGS.some((r) => x.id.endsWith(r)))
    .slice(0, n).map((x) => x.reason)
}

const RUNGS = ['.model', '.calibration', '.validation', '.operational']

// Model work that has been recorded for a capability (a model, its calibration, its validation), passed or not, in plain
// words. A validation that missed the criterion it stated beforehand is listed here, and the state stays below it.
export function modelRecords(c: ReadinessCapability): string[] {
  return c.checks.filter((x) => RUNGS.some((r) => x.id.endsWith(r)) && !x.reason.startsWith('No ')).map((x) => x.reason)
}

export const stateClass = (s: string) => (s === 'NOT AVAILABLE' ? 'blocked' : s === 'CONTEXT ONLY' ? 'context' : s.startsWith('DATA') ? 'partial' : 'progress')
