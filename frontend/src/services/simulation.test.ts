import { describe, expect, it } from 'vitest'
import { coherence, count, type SimData, type SimProps } from './simulation'

const feature = (properties: SimProps) => ({ type: 'Feature' as const, properties, geometry: { type: 'Point' as const, coordinates: [0, 0] } })
const data = { features: { type: 'FeatureCollection', features: [
  feature({ k: 'c', km: 0, h: 0 }),
  feature({ k: 'b', km: 5, h: 10 }),
  feature({ k: 'b', km: 5, h: 40 }),
  feature({ k: 'b', km: 50, h: 10 }),
  feature({ k: 'a', km: 5, h: 90, len: 2 }),
  feature({ k: 'r', km: 5, h: 10, len: 3 }),
  feature({ k: 'p', km: 5, h: 10, name: 'Low' }),
  feature({ k: 'p', km: 5, h: 90, name: 'High' }),
] } } as unknown as SimData

describe('count', () => {
  it('the replay counts what was mapped as affected up to that point, at any height', () => {
    expect(count(data, 10)).toEqual({ buildings: 2, roadKm: 2, places: ['Low', 'High'] })
  })
  it('the what-if counts only what sits below the water and within reach', () => {
    expect(count(data, 10, 20)).toEqual({ buildings: 1, roadKm: 3, places: ['Low'] })
    expect(count(data, 60, 20).buildings).toBe(2)
  })
})

describe('coherence', () => {
  it('is 1 on unchanged ground and falls as the ground changes', () => {
    expect(coherence(0)).toBeCloseTo(1)
    expect(coherence(0.5)).toBeLessThan(coherence(0.2))
    expect(coherence(1)).toBeLessThan(0.15)
  })
})
