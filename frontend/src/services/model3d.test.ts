import { readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { EVIDENCE } from './evidence'
import { CASES } from './manifest'

// The Rasuwa 3D model (prepare_rasuwa_3d.py): every layer names its evidence class and its source, nothing is a forecast,
// and every file it points to is shipped.
const PUBLIC = join(__dirname, '../../public')
const url = CASES.find((c) => c.model3d)?.model3d
const model = url ? JSON.parse(readFileSync(join(PUBLIC, url), 'utf-8')) : null

describe('Rasuwa 3D model', () => {
  it('is listed for a case', () => expect(model).not.toBeNull())
  it('stands on NASA terrain: NASADEM heights', () => {
    expect(model.baseLayer.attribution).toMatch(/NASADEM/)
    expect(model.baseLayer.attribution).toMatch(/NASA/)
  })
  it('has heights of the right size', () => {
    expect(statSync(join(PUBLIC, model.heights)).size).toBe(model.width * model.height * 2)
    expect(model.minM).toBeLessThan(model.maxM)
  })
  it('gives every layer, track and label an evidence class, and none is a forecast or scenario', () => {
    const all = [model.baseLayer, model.placesLayer, ...model.layers, ...model.tracks, ...model.markers]
    for (const x of all) {
      expect(Object.keys(EVIDENCE)).toContain(x.evidence)
      expect(['forecast', 'simulation']).not.toContain(x.evidence)
    }
  })
  it('keeps the source caveats and attribution on every draped layer', () => {
    for (const l of model.layers) {
      expect(l.attribution, l.id).toBeTruthy()
      expect(Array.isArray(l.limitations), l.id).toBe(true)
      expect(statSync(join(PUBLIC, l.file)).size, l.file).toBeGreaterThan(0)
    }
    expect(model.layers.filter((l: { id: string }) => l.id.startsWith('unosat')).every((l: { limitations: string[] }) => l.limitations.some((x) => /Not yet field validated/.test(x)))).toBe(true)
  })
  it('labels measured radar layers as observed, change layers as derived, and the viewing directions as derived', () => {
    const radar = model.layers.filter((l: { group?: string }) => l.group === 'radar')
    for (const l of radar) expect(l.evidence, l.id).toBe(l.kind === 'change' ? 'derived' : 'observed')
    expect(radar.filter((l: { kind: string }) => l.kind === 'coherence')).toHaveLength(2)
    expect(radar.filter((l: { kind: string }) => l.kind === 'backscatter').length).toBeGreaterThan(0)
    expect(radar.every((l: { note?: string; short?: string }) => l.note && l.short)).toBe(true)
    expect(model.tracks.map((t: { track: number; evidence: string }) => [t.track, t.evidence])).toEqual([[48, 'derived'], [98, 'derived']])
  })
})
