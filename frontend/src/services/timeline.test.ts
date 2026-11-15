import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { Manifest } from '../types/manifest'
import { stepKind, stepLabel } from './timeLabels'

// P0.5: coherence through time at any clicked spot. The shipped layer must hold every frame 74 pair in order, each step
// read from its own granule, so the inspector chart shows one stored value per pair and nothing in between.
const data = resolve(__dirname, '../../public/data')
const shipped = JSON.parse(readFileSync(resolve(data, 'manifests/manifest.json'), 'utf8')) as Manifest
const layer = shipped.layers.find((l) => l.id === 'rasuwa-2026:coherence-timeline')
const compact = (iso: string) => iso.replace(/-/g, '')

describe('coherence through time (shipped Rasuwa layer)', () => {
  it('holds the five Track 48 pairs, 23 Jul to 3 Oct 2026, over frames 74 and 75, as consecutive pair steps', () => {
    const steps = layer?.timeSteps ?? []
    expect(layer?.frames).toEqual([74, 75])
    expect(layer?.name).toBe('Coherence through time (Track 48, frames 74 and 75)')
    expect(steps.map((s) => s.label)).toEqual([
      '2026-07-23/2026-08-16', '2026-08-16/2026-08-28', '2026-08-28/2026-09-09', '2026-09-09/2026-09-21', '2026-09-21/2026-10-03',
    ])
    expect(stepKind(steps.map((s) => s.label))).toBe('pairs')
    for (let i = 1; i < steps.length; i++) expect(steps[i].label.split('/')[0]).toBe(steps[i - 1].label.split('/')[1])
    expect(stepLabel(steps[1].label)).toBe('16–28 Aug')
  })

  it('reads each step from that pair\'s own granule in each frame, with its sampling raster and validity on disk', () => {
    for (const step of layer?.timeSteps ?? []) {
      const [ref, sec] = step.label.split('/').map(compact)
      expect(step.sources.map((s) => s.frame).sort()).toEqual([74, 75])
      for (const src of step.sources) {
        expect(src.granule).toMatch(new RegExp(`_048_D_0${src.frame}_\\d{3}_\\d{4}_\\w{2}_${ref}T\\d{6}_${ref}T\\d{6}_${sec}T\\d{6}_${sec}T\\d{6}_`))
        expect(src.sourceDataset).toMatch(/unwrappedInterferogram\/HH\/coherenceMagnitude$/)
        for (const f of [src.sampling, src.validity]) expect(existsSync(resolve(data, String(f).replace(/^data\//, ''))), String(f)).toBe(true)
      }
    }
  })
})

describe('coherence through time from the opposite side (shipped Track 98 layer)', () => {
  const t98 = shipped.layers.find((l) => l.id === 'rasuwa-2026:coherence-timeline-t98')
  it('holds the five frame 16 pairs, 26 Jul to 6 Oct 2026, beside the Track 48 series, never replacing it', () => {
    expect(t98?.track).toBe(98)
    expect(t98?.orbitDirection).toBe('ASCENDING')
    expect(t98?.frames).toEqual([16])
    expect(t98?.timeSteps?.map((s) => s.label)).toEqual([
      '2026-07-26/2026-08-19', '2026-08-19/2026-08-31', '2026-08-31/2026-09-12', '2026-09-12/2026-09-24', '2026-09-24/2026-10-06',
    ])
    expect(layer?.track).toBe(48)
    for (const step of t98?.timeSteps ?? []) {
      const [ref, sec] = step.label.split('/').map(compact)
      expect(step.sources[0].granule).toMatch(new RegExp(`_098_A_016_.*_${ref}T\\d{6}_${ref}T\\d{6}_${sec}T\\d{6}_${sec}T\\d{6}_`))
      for (const f of [step.sources[0].sampling, step.sources[0].validity]) expect(existsSync(resolve(data, String(f).replace(/^data\//, ''))), String(f)).toBe(true)
    }
  })
})
