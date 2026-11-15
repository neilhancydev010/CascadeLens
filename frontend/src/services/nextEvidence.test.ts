import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { Manifest } from '../types/manifest'
import { FLAG } from './observability'
import { nextSteps, type ViewFlags } from './nextEvidence'

// The rule table is checked against the shipped Rasuwa manifest, so "available" means a layer really ships.
const shipped = JSON.parse(readFileSync(resolve(__dirname, '../../public/data/manifests/manifest.json'), 'utf8')) as Manifest
const layers = shipped.layers
const v48 = (flags: number | null): ViewFlags => ({ label: 'Track 48, frames 74 and 75', track: 48, flags })
const v98 = (flags: number | null): ViewFlags => ({ label: 'Track 98, frame 16', track: 98, flags })

describe('evidence gap → next observation', () => {
  it('points to the other viewing direction only where that direction is usable', () => {
    const a = v48(FLAG.productMasked), b = v98(0)
    const steps = nextSteps('disturbance', a, [a, b], layers)
    expect(steps.find((s) => s.rule === 'R-MASK')).toMatchObject({ availability: 'available' })
    const bad = v98(FLAG.shadow)
    expect(nextSteps('disturbance', a, [a, bad], layers).find((s) => s.rule === 'R-MASK')).toMatchObject({ availability: 'not-found' })
  })

  it('never claims a neighbouring acquisition exists when none is processed', () => {
    const a = v48(FLAG.outside)
    const s = nextSteps('movement', a, [a], layers).find((x) => x.rule === 'R-OUTSIDE')!
    expect(s.availability).toBe('not-found')
    expect(s.detail).toMatch(/none has been found/)
  })

  it('points to the loaded Track 48 GCOV snapshots and change, and lists a track with only catalogue records as catalogued', () => {
    const a = v48(FLAG.productMasked)
    const s = nextSteps('disturbance', a, [a], layers).find((x) => x.rule === 'R-MASK-GCOV')!
    expect(s.availability).toBe('available')
    expect(s.detail).toMatch(/2026-08-16 to 2026-08-28/)
    const onlyCatalogued = layers.map((l) => (l.productType === 'GCOV' || l.measurementType === 'gcov-change') && l.track === 48 ? { ...l, status: 'catalogued' as const } : l)
    expect(nextSteps('disturbance', a, [a], onlyCatalogued).find((x) => x.rule === 'R-MASK-GCOV')).toMatchObject({ availability: 'catalogued' })
  })

  it('does not turn missing phase into movement, and points to the loaded offsets', () => {
    const a = v48(FLAG.noUnwrapped)
    const s = nextSteps('movement', a, [a], layers).find((x) => x.rule === 'R-PHASE')!
    expect(s.availability).toBe('available')
    expect(s.step).toMatch(/Do not infer movement/)
    expect(s.detail).toMatch(/not converted to movement/)
  })

  it('suggests other pairs of the same track for a poor baseline', () => {
    const a = v48(FLAG.lowBaseline)
    expect(nextSteps('disturbance', a, [a], layers).find((s) => s.rule === 'R-BASELINE')).toMatchObject({ availability: 'available' })
  })

  it('keeps the timing caveat for a usable spot and asks for nothing else', () => {
    const a = v48(0)
    const steps = nextSteps('disturbance', a, [a], layers)
    expect(steps.map((s) => s.rule)).toEqual(['R-TIMING'])
    expect(steps[0].detail).toMatch(/cannot date the change or establish its cause/)
    expect(nextSteps('movement', a, [a], layers)).toEqual([])
  })

  it('ends every unusable answer with a step for a person, and gives the same answer every time', () => {
    const a = v48(FLAG.layover | FLAG.lowCoherence), b = v98(FLAG.outside)
    const one = nextSteps('movement', a, [a, b], layers)
    expect(one.at(-1)?.availability).toBe('human')
    expect(nextSteps('movement', a, [a, b], layers)).toEqual(one)
  })
})
