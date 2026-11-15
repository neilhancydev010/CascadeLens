import { describe, expect, it } from 'vitest'
import { canPan, centreToSlider, clampCentre, sliderToCentre, zoomCeiling } from './viewMath'

describe('view slider maths', () => {
  it('maps the slider ends to the furthest centres that keep the view inside', () => {
    // Range 0 to 10, view 4 wide: the centre can sit from 2 to 8
    expect(sliderToCentre(0, 0, 10, 4)).toBe(2)
    expect(sliderToCentre(1, 0, 10, 4)).toBe(8)
    expect(sliderToCentre(0.5, 0, 10, 4)).toBe(5)
  })

  it('never lets the view leave the range, whatever the slider says', () => {
    for (const t of [-1, -0.2, 0, 0.3, 0.9, 1, 2]) {
      const c = sliderToCentre(t, 0, 10, 4)
      expect(c - 2).toBeGreaterThanOrEqual(0)
      expect(c + 2).toBeLessThanOrEqual(10)
    }
  })

  it('round-trips between slider and centre', () => {
    for (const t of [0, 0.25, 0.5, 0.8, 1]) expect(centreToSlider(sliderToCentre(t, -3, 7, 2.5), -3, 7, 2.5)).toBeCloseTo(t, 12)
  })

  it('clamps a centre that would show ground outside the range', () => {
    expect(clampCentre(9.5, 0, 10, 4)).toBe(8)
    expect(clampCentre(-1, 0, 10, 4)).toBe(2)
    expect(clampCentre(5, 0, 10, 4)).toBe(5)
  })

  it('has nothing to pan when the whole range is in view', () => {
    expect(canPan(0, 10, 10)).toBe(false)
    expect(canPan(0, 10, 12)).toBe(false)
    expect(canPan(0, 10, 9.9)).toBe(true)
    expect(sliderToCentre(0, 0, 10, 12)).toBe(5)
    expect(clampCentre(1, 0, 10, 12)).toBe(5)
    expect(centreToSlider(1, 0, 10, 12)).toBe(0.5)
  })

  it('reads a centre beyond the allowed span as the nearer end', () => {
    expect(centreToSlider(100, 0, 10, 4)).toBe(1)
    expect(centreToSlider(-100, 0, 10, 4)).toBe(0)
  })

  it('caps the deepest zoom at the tiles, and at five levels past the whole area', () => {
    expect(zoomCeiling(9.2, 12)).toBe(12)
    expect(zoomCeiling(9.2, 16)).toBeCloseTo(14.2)
    expect(zoomCeiling(9.2, undefined)).toBeCloseTo(14.2)
    expect(zoomCeiling(9.2, 8)).toBe(9.2) // Tiles shallower than the whole-area view: the slider has no range, never a negative one
  })
})

describe('Mercator helpers', () => {
  it('round-trip longitude and latitude', async () => {
    const { mercX, mercY, lngOf, latOf } = await import('./viewMath')
    expect(lngOf(mercX(85.3))).toBeCloseTo(85.3, 10)
    expect(latOf(mercY(28.2))).toBeCloseTo(28.2, 10)
    expect(mercY(28.3)).toBeLessThan(mercY(28.2)) // North is up the screen, so a smaller y
  })
})
