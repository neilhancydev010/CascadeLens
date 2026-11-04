// @vitest-environment node
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fromArrayBuffer } from 'geotiff'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Layer } from '../types/manifest'
import { classify, clearSamplerCache, pixelIndex, projectionFor, samplePoint } from './sampler'

vi.mock('./manifest', async (orig) => ({ ...(await orig<typeof import('./manifest')>()), assetUrl: (p: string) => p }))

const open = async (p: string) => {
  const b = readFileSync(resolve(__dirname, '../../public', p))
  return fromArrayBuffer(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer)
}

const dem = {
  id: 'context:terrain', status: 'sampleable',
  sources: [{ frame: null, granule: 'Copernicus DEM GLO-30', sampling: 'data/sampling/context/copdem_glo30.tif', validity: 'data/sampling/context/copdem_glo30_validity.tif' }],
} as unknown as Layer

describe('sampler on the real Copernicus DEM COG', () => {
  beforeEach(clearSamplerCache)

  // Expected values were read independently with rasterio.
  it.each([
    [85.3515, 28.1625, 1846.493896484375, 675, 3434],
    [85.5, 28.3, 3866.430908203125, 180, 3968],
    [85.0, 27.85, 616.4324951171875, 1800, 2168],
  ])('reads the stored value at %f, %f', async (lng, lat, value, row, col) => {
    const r = await samplePoint(dem, lng, lat, open)
    expect(r.state).toBe('valid')
    expect(r.value).toBeCloseTo(value, 3)
    expect([r.row, r.col]).toEqual([row, col])
  })

  it('reports outside coverage rather than a number', async () => {
    const r = await samplePoint(dem, 80, 20, open)
    expect(r.state).toBe('outside')
    expect(r.value).toBeUndefined()
  })

  it('recovers from a transient read failure', async () => {
    let calls = 0
    const flaky = (p: string) => (++calls === 1 ? Promise.reject(new Error('dropped')) : open(p))
    const r = await samplePoint(dem, 85.3515, 28.1625, flaky)
    expect(r.state).toBe('valid')
    expect(calls).toBeGreaterThan(1)
  })

  it('gives up after repeated failures rather than retrying forever', async () => {
    let calls = 0
    const down = () => { calls++; return Promise.reject(new Error('down')) }
    const r = await samplePoint(dem, 85.3515, 28.1625, down)
    expect(r.state).toBe('error')
    expect(calls).toBeLessThan(10)
  })

  it('explains that a picture layer cannot be sampled', async () => {
    const r = await samplePoint({ ...dem, status: 'renderable', sources: [{ tiles: {} }] } as unknown as Layer, 85, 28, open)
    expect(r.state).toBe('unavailable')
    expect(r.message).toContain('no stored values')
  })

  it('reports a failed asset as a sampling failure', async () => {
    const r = await samplePoint({ ...dem, sources: [{ ...dem.sources[0], sampling: 'data/missing.tif' }] }, 85, 28, open)
    expect(r.state).toBe('error')
    expect(r.value).toBeUndefined()
  })

  it('does not sample a catalogue-only layer', async () => {
    const r = await samplePoint({ ...dem, status: 'catalogued', sources: [] }, 85, 28, open)
    expect(r.state).toBe('unavailable')
  })
})

describe('validity classification', () => {
  it('never turns missing data into a value', () => {
    expect(classify(1.5, 1)).toBe('valid')
    expect(classify(1.5, 2)).toBe('masked')
    expect(classify(1.5, 0)).toBe('nodata')
    expect(classify(NaN, 1)).toBe('nodata')
    expect(classify(Infinity, 2)).toBe('nodata')
    expect(classify(0, 1)).toBe('valid')
  })
})

describe('geometry', () => {
  it('projects to UTM 45N', () => {
    const [x, y] = projectionFor(32645)(87, 28)
    expect(x).toBeCloseTo(500000, 3) // Central meridian. Northing below is pyproj's value for the same point
    expect(y).toBeCloseTo(3097202.3707, 3)
  })

  it('refuses a CRS it cannot transform', () => {
    expect(() => projectionFor(3413)).toThrow(/Unsupported/)
  })

  it('uses pixel edges, so a point just inside a pixel stays in it', () => {
    const image = { getOrigin: () => [100, 200, 0], getResolution: () => [10, -10, 0] }
    expect(pixelIndex(image, 100, 200)).toEqual({ col: 0, row: 0 })
    expect(pixelIndex(image, 109.9, 190.1)).toEqual({ col: 0, row: 0 })
    expect(pixelIndex(image, 110, 190)).toEqual({ col: 1, row: 1 })
    expect(pixelIndex(image, 99, 201)).toEqual({ col: -1, row: -1 })
  })
})
