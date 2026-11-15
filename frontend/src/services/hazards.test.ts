import { describe, expect, it } from 'vitest'
import { distanceM, terrainClass, terrainFactors, TFLAG } from './hazards'

describe('terrain screen', () => {
  it('classes match the processing rules', () => {
    expect(terrainClass(0)).toBe(1)
    expect(terrainClass(TFLAG.slope15)).toBe(1)
    expect(terrainClass(TFLAG.slope15 | TFLAG.hollow)).toBe(2)
    expect(terrainClass(TFLAG.slope25)).toBe(2)
    expect(terrainClass(TFLAG.slope25 | TFLAG.wet)).toBe(3)
    expect(terrainClass(TFLAG.slope35 | TFLAG.hollow)).toBe(3)
    expect(terrainClass(TFLAG.slope35 | TFLAG.hollow | TFLAG.wet)).toBe(4)
  })
  it('names every factor', () => {
    expect(terrainFactors(TFLAG.slope35 | TFLAG.hollow | TFLAG.wet)).toHaveLength(3)
    expect(terrainFactors(0)[0]).toMatch(/Gentle/)
  })
})

describe('road distance', () => {
  it('measures to the nearest point of a segment in metres', () => {
    const line: [number, number][] = [[85, 28], [85.01, 28]]
    expect(distanceM([85.005, 28.001], line)).toBeGreaterThan(105)
    expect(distanceM([85.005, 28.001], line)).toBeLessThan(115)
    expect(distanceM([85.02, 28], line)).toBeGreaterThan(900)
  })
})
