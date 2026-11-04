import type { GeoTIFF, GeoTIFFImage } from 'geotiff'
import proj4 from 'proj4'
import type { Layer, RasterSource } from '../types/manifest'
import { assetUrl, isUsable } from './manifest'

// Reads the value stored in the sampling COG, nearest native pixel, no interpolation. Never derived from a tile colour.
export type SampleState = 'valid' | 'masked' | 'nodata' | 'outside' | 'unavailable' | 'error'

export interface SampleResult {
  state: SampleState
  value?: number
  frame?: number | null
  granule?: string
  row?: number
  col?: number
  message: string
}

export const MESSAGE: Record<SampleState, string> = {
  valid: 'Valid measurement.',
  masked: 'Masked measurement: the stored value is shown, but it failed a quality rule.',
  nodata: 'No valid observation at this location.',
  outside: 'Outside product coverage.',
  unavailable: 'No sampling asset exists for this layer.',
  error: 'Sampling failed.',
}

// Classes written by processing/src/cascade_lens/quality.py
const VALID = 1
const MASKED = 2

export type Opener = (path: string) => Promise<GeoTIFF>
const openRemote: Opener = async (path) => (await import('geotiff')).fromUrl(assetUrl(path)) // Loaded on the first click, not at startup

interface OpenRaster { image: GeoTIFFImage; toRaster: (lng: number, lat: number) => [number, number] }

const cache = new Map<string, Promise<OpenRaster>>()

export function projectionFor(epsg: number): (lng: number, lat: number) => [number, number] {
  if (epsg === 4326) return (lng, lat) => [lng, lat]
  const zone = epsg % 100
  if ((epsg > 32600 && epsg <= 32660) || (epsg > 32700 && epsg <= 32760)) {
    const def = `+proj=utm +zone=${zone}${epsg > 32700 ? ' +south' : ''} +datum=WGS84 +units=m +no_defs`
    return (lng, lat) => proj4('WGS84', def, [lng, lat]) as [number, number]
  }
  throw new Error(`Unsupported raster CRS EPSG:${epsg}`) // NISAR polar grids are not used over Nepal; fail rather than guess
}

async function open(path: string, opener: Opener) {
  let p = cache.get(path)
  if (!p) {
    p = opener(path).then(async (tiff) => {
      const image = await tiff.getImage(0)
      const keys = image.getGeoKeys()
      const epsg = Number(keys?.ProjectedCSTypeGeoKey ?? keys?.GeographicTypeGeoKey)
      if (!epsg) throw new Error(`No CRS in ${path}`)
      return { image, toRaster: projectionFor(epsg) }
    })
    p.catch(() => cache.delete(path))
    cache.set(path, p)
  }
  return p
}

async function pixel(r: OpenRaster, row: number, col: number): Promise<number> {
  const out = await r.image.readRasters({ window: [col, row, col + 1, row + 1], samples: [0], interleave: true })
  return Number((out as unknown as ArrayLike<number>)[0])
}

export function pixelIndex(image: Pick<GeoTIFFImage, 'getOrigin' | 'getResolution'>, x: number, y: number) {
  const [ox, oy] = image.getOrigin()
  const [sx, sy] = image.getResolution()
  return { col: Math.floor((x - ox) / sx) + 0, row: Math.floor((y - oy) / sy) + 0 } // + 0 normalises -0
}

export function classify(value: number, validity: number): SampleState {
  if (!Number.isFinite(value) || (validity !== VALID && validity !== MASKED)) return 'nodata'
  return validity === MASKED ? 'masked' : 'valid'
}

async function sampleSource(s: RasterSource, lng: number, lat: number, opener: Opener): Promise<SampleResult> {
  const raster = await open(s.sampling!, opener)
  const [x, y] = raster.toRaster(lng, lat)
  const { col, row } = pixelIndex(raster.image, x, y)
  if (col < 0 || row < 0 || col >= raster.image.getWidth() || row >= raster.image.getHeight())
    return { state: 'outside', message: MESSAGE.outside }
  const [value, validity] = await Promise.all([pixel(raster, row, col), open(s.validity!, opener).then((v) => pixel(v, row, col))])
  const state = classify(value, validity)
  const stored = state === 'nodata' ? undefined : value
  return { state, value: stored, frame: s.frame, granule: s.granule, row, col, message: MESSAGE[state] }
}

const RANK: SampleState[] = ['valid', 'masked', 'nodata', 'outside']
const ATTEMPTS = 3

export async function samplePoint(layer: Layer, lng: number, lat: number, opener: Opener = openRemote): Promise<SampleResult> {
  if (layer.status === 'renderable') return { state: 'unavailable', message: 'This layer is a picture with no stored values, so it cannot be sampled.' }
  if (!isUsable(layer) || !layer.sources.some((s) => s.sampling)) return { state: 'unavailable', message: MESSAGE.unavailable }
  // Range requests occasionally fail in transit (seen on 1 in 6 first reads from `vite preview`), so reopen and retry.
  for (let attempt = 1; ; attempt++) {
    try {
      // Frames are not mosaicked. A point in an overlap reports the first frame holding a valid pixel.
      const results = await Promise.all(layer.sources.map((s) => sampleSource(s, lng, lat, opener)))
      return results.reduce((a, b) => (RANK.indexOf(b.state) < RANK.indexOf(a.state) ? b : a))
    } catch (e) {
      if (attempt === ATTEMPTS) return { state: 'error', message: `${MESSAGE.error} ${e instanceof Error ? e.message : ''}`.trim() }
      layer.sources.forEach((s) => { cache.delete(s.sampling!); cache.delete(s.validity!) })
    }
  }
}

export const clearSamplerCache = () => cache.clear()
