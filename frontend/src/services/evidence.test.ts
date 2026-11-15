import { describe, expect, it } from 'vitest'
import type { Layer } from '../types/manifest'
import { evidenceOf } from './evidence'

const L = (o: Partial<Layer>) => ({ id: 'x', productType: '', measurementType: '', measurementClass: 'measurement', status: 'sampleable', sources: [{}], ...o }) as unknown as Layer

describe('evidence classes', () => {
  it('labels each kind of layer', () => {
    expect(evidenceOf(L({}))).toBe('observed')
    expect(evidenceOf(L({ measurementClass: 'derived' }))).toBe('derived')
    expect(evidenceOf(L({ measurementClass: 'reference map' }))).toBe('reference')
    expect(evidenceOf(L({ id: 'ref:scenario-extent', measurementClass: 'derived' }))).toBe('simulation')
  })
  it('calls an unavailable layer unknown, never safe', () => {
    expect(evidenceOf(L({ status: 'catalogued', sources: [] }))).toBe('unknown')
  })
})
