import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Layer, Manifest } from '../types/manifest'
import { buildStory } from '../data/story'
import { App } from './App'

// jsdom has no WebGL: the real map is exercised in the browser, see docs/SCIENTIFIC_VALIDATION.md.
const map = vi.hoisted(() => ({ last: {} as Record<string, unknown> }))
vi.mock('../components/map/MapView', () => ({
  MapView: (p: Record<string, unknown>) => { map.last = p; return <button data-testid="map" onClick={() => (p.onPoint as (x: [number, number]) => void)([85.35, 28.16])}>map</button> },
}))
vi.mock('../services/sampler', async (orig) => ({
  ...(await orig<typeof import('../services/sampler')>()),
  samplePoint: vi.fn(async (l: Layer) => l.id === 'context:terrain'
    ? { state: 'valid', value: 1846.49, frame: null, granule: 'Copernicus DEM GLO-30', row: 1, col: 2, message: 'Valid measurement.' }
    : { state: 'nodata', message: 'No valid observation at this location.' }),
}))

const shipped = () => JSON.parse(readFileSync(resolve(__dirname, '../../public/data/manifests/manifest.json'), 'utf8')) as Manifest

// The state before any NISAR file is processed, kept under test because a failed QA gate returns the app to it.
function noNisar(): Manifest {
  const m = shipped()
  const reason = 'Listed in the ASF catalogue, not retrieved. NASA Earthdata Login required to download it.'
  m.layers = m.layers.filter((l) => l.category !== 'preview')
  for (const l of m.layers.filter((x) => x.mission === 'NISAR')) Object.assign(l, { status: 'catalogued', statusReason: reason, sources: [], stats: undefined, legend: undefined })
  m.groups.forEach((g) => { g.available = false; g.statusReason = reason })
  m.analysis = undefined
  return m
}

function withUsablePhase(): Manifest {
  const m = noNisar()
  for (const id of ['pair-a:gunw-phase', 'pair-a:gunw-coherence']) {
    const p = m.layers.find((l) => l.id === id)!
    p.status = 'sampleable'
    p.statusReason = null
    p.sources = [{ frame: 74, granule: 'G', sourceFilename: 'G.h5', bounds: [85, 28, 85.5, 28.3], validFraction: 0.5, sampling: 's.tif', validity: 'v.tif', tiles: { url: 't/{z}/{x}/{y}.png', minzoom: 8, maxzoom: 11, count: 1 } }]
    p.legend = { type: 'continuous', stops: ['#000', '#fff'], min: -3, max: 3, unit: 'radians' }
  }
  m.groups[0].available = true
  return m
}

function start(m: Manifest | null) {
  vi.stubGlobal('fetch', vi.fn(async () => (m ? { ok: true, json: async () => m } : { ok: false, status: 404 })))
  render(<App />)
}

beforeEach(() => { window.matchMedia = vi.fn().mockReturnValue({ matches: false }) as never })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('application states', () => {
  it('reports a failed start rather than an empty map', async () => {
    start(null)
    expect(await screen.findByText(/could not start/)).toBeTruthy()
    expect(screen.getByText(/HTTP 404/)).toBeTruthy()
  })

  it('opens directly on the Rasuwa case with the primary pair', async () => {
    start(noNisar())
    expect(await screen.findByText(/Rasuwa–Bhote Koshi–Trishuli/)).toBeTruthy()
    expect(screen.getByRole('radio', { name: /16–28 August 2026/ })).toHaveProperty('checked', true)
  })
})

describe('honest layer availability', () => {
  it('disables catalogue-only NISAR layers and says why', async () => {
    start(noNisar())
    const phase = await screen.findByRole('radio', { name: /Unwrapped phase/ })
    expect(phase).toHaveProperty('disabled', true)
    expect(within(phase.closest('label')!).getByText('Download required')).toBeTruthy()
    expect(screen.getByRole('radio', { name: /19–31 August 2026/ })).toHaveProperty('disabled', true)
    expect(screen.getAllByText(/Earthdata Login required/).length).toBeGreaterThan(0)
  })

  it('offers a layer once the manifest says it is usable, and updates the panels', async () => {
    start(withUsablePhase())
    await screen.findByRole('radio', { name: /Unwrapped phase/ })
    expect(screen.getByRole('radio', { name: /Unwrapped phase/ })).toHaveProperty('checked', true)
    expect((map.last.active as Layer).id).toBe('pair-a:gunw-phase')
    expect(screen.getAllByText(/Phase is not displacement/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Unwrapped phase \(radians\)/)).toBeTruthy()
    fireEvent.click(screen.getByRole('radio', { name: /Terrain elevation/ }))
    expect((map.last.active as Layer).id).toBe('context:terrain')
    expect(screen.queryByText(/Unwrapped phase \(radians\)/)).toBeNull()
    expect(screen.getByText(/Terrain elevation \(m\)/)).toBeTruthy()
  })

  it('switches evidence views without changing the selected point', async () => {
    start(withUsablePhase())
    fireEvent.click(await screen.findByTestId('map'))
    fireEvent.click(screen.getByRole('tab', { name: 'Pixel offsets' }))
    expect(screen.getByRole('radio', { name: /Slant-range offset/ })).toBeTruthy()
    expect(map.last.point).toEqual([85.35, 28.16])
  })
})

describe('bookmarks and references', () => {
  it('moves the map to each bookmark and marks it active', async () => {
    const m = noNisar()
    start(m)
    for (const b of m.bookmarks) {
      const btn = await screen.findByRole('button', { name: b.name })
      fireEvent.click(btn)
      expect((map.last.focus as { bounds: number[] }).bounds).toEqual(b.bounds)
      expect(btn.getAttribute('aria-pressed')).toBe('true')
    }
  })

  it('toggles a reference layer on the real map props', async () => {
    start(noNisar())
    const box = await screen.findByRole('checkbox', { name: /barrier lakes/ })
    expect((map.last.references as Layer[]).some((l) => l.id === 'ref:unosat-lakes')).toBe(false)
    fireEvent.click(box)
    expect((map.last.references as Layer[]).some((l) => l.id === 'ref:unosat-lakes')).toBe(true)
  })
})

describe('inspector', () => {
  it('shows a real sample with its context', async () => {
    start(noNisar())
    fireEvent.click(await screen.findByTestId('map'))
    expect(await screen.findByText('Valid measurement.')).toBeTruthy()
    expect(screen.getByText(/1846\.5/)).toBeTruthy()
    expect(within(document.querySelector<HTMLElement>('.inspector')!).getByText('Bhote Koshi corridor')).toBeTruthy()
  })

  it('shows no number where there is no observation', async () => {
    start(withUsablePhase())
    fireEvent.click(await screen.findByTestId('map'))
    await waitFor(() => expect(document.querySelector('.sample')?.textContent).toBe('No valid observation at this location.'))
    expect(document.querySelector('.value')).toBeNull()
  })
})

describe('story', () => {
  it('runs all four steps and exits', async () => {
    start(noNisar())
    fireEvent.click(await screen.findByRole('button', { name: 'Start the guided story' }))
    for (const title of ['1. The source', '2. The radar evidence', '3. The downstream corridor']) {
      expect(screen.getByRole('heading', { name: title })).toBeTruthy()
      fireEvent.click(screen.getByRole('button', { name: /^Next/ }))
    }
    expect(screen.getByRole('heading', { name: '4. Scientific interpretation' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Explore the map' }))
    expect(screen.queryByRole('heading', { name: /Scientific interpretation/ })).toBeNull()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start the guided story' })).toHaveProperty('disabled', false))
  })

  it('never claims a result that is not loaded', () => {
    const text = buildStory(noNisar()).flatMap((s) => s.paragraphs).join(' ')
    expect(text).toContain('no phase or coherence is shown')
    expect(text).toContain('no NISAR measurement is loaded')
    expect(buildStory(noNisar()).every((s) => s.layerId === 'context:terrain')).toBe(true)
    const withData = buildStory(withUsablePhase())
    expect(withData[1].layerId).toBe('pair-a:gunw-coherence')
    expect(withData.flatMap((s) => s.paragraphs).join(' ')).not.toContain('no phase or coherence is shown')
  })

  it('quotes figures from the analysis, never fixed numbers', () => {
    const m = withUsablePhase()
    const zones = { 'gunw-coherence': { 'mapped extent': { pixels: 9, median: 0.11 }, '1 km ring outside extent': { pixels: 9, median: 0.77 }, 'detachment zone': { pixels: 5, validPct: 0 } } }
    m.analysis = { 'pair-a': { frames: { f074: { ionosphere: { pearsonR: 0.9, stdPhase: 8, stdPhaseMinusIono: 4 }, zones } } } }
    const text = buildStory(m).flatMap((s) => s.paragraphs).join(' ')
    expect(text).toContain('0.11 against 0.77 in frame 74')
    expect(text).toContain('gap between radar swaths')
    expect(text).toContain('from 8 to 4 radians in frame 74')
    zones['gunw-coherence']['detachment zone'].validPct = 40
    expect(buildStory(m).flatMap((s) => s.paragraphs).join(' ')).not.toContain('gap between radar swaths')
  })

  it('does not claim a displacement anywhere', () => {
    const text = buildStory(shipped()).flatMap((s) => s.paragraphs).join(' ')
    expect(text).toContain('No displacement is calculated')
  })
})
