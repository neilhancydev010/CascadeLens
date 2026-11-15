import { describe, expect, it } from 'vitest'
import { stepKind, stepLabel } from './timeLabels'

describe('time-step labels', () => {
  it('shows dates and date pairs as days, never as the first two digits of the year', () => {
    expect(stepLabel('2026-08-16')).toBe('16 Aug')
    expect(stepLabel('2026-08-16/2026-08-28')).toBe('16–28 Aug')
    expect(stepLabel('2026-07-23/2026-08-16')).toBe('23 Jul–16 Aug')
  })
  it('names what the axis spans', () => {
    expect(stepKind(['2026-08-16', '2026-08-28'])).toBe('dates')
    expect(stepKind(['2026-07-23/2026-08-16', '2026-08-16/2026-08-28'])).toBe('pairs')
    expect(stepKind(['00 UTC', '03 UTC'])).toBe('hours')
  })
})
