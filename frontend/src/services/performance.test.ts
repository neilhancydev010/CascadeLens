import { browserSpeed, describeSpeed, describeWait, FIRST_VIEW_BYTES, lite, looksLowEnd, measuredSpeed, remainingSeconds } from './performance'

const entry = (startTime: number, responseEnd: number, transferSize: number) => ({ startTime, responseEnd, transferSize }) as unknown as PerformanceEntry

describe('connection speed', () => {
  it('divides the bytes that came over the network by the wall time they took, side by side', () => {
    // 200 KB and 100 KB downloading at the same time over 5 seconds: 60 KB/s, not the sum of two rates
    const s = measuredSpeed([entry(0, 5000, 200_000), entry(1000, 4000, 100_000)])!
    expect(s.bytesPerSecond).toBeCloseTo(60_000)
    expect(s.received).toBe(300_000)
  })

  it('ignores cached files, so a return visit is not called slow', () => {
    expect(measuredSpeed([entry(0, 9000, 0), entry(0, 9000, 120)])).toBeNull()
  })

  it('does not judge from too little', () => {
    expect(measuredSpeed([entry(0, 2000, 20_000)])).toBeNull()
  })

  it('reads what the browser reports, when it reports anything', () => {
    expect(browserSpeed({ effectiveType: '2g' })!.bytesPerSecond).toBe(30_000)
    expect(browserSpeed({ effectiveType: '4g', downlink: 0.4 })!.bytesPerSecond).toBe(50_000)
    expect(browserSpeed({})).toBeNull()
    expect(browserSpeed(undefined)).toBeNull()
  })

  it('estimates the wait for the rest of the first view, in plain words', () => {
    expect(remainingSeconds({ bytesPerSecond: 20_000, received: FIRST_VIEW_BYTES - 2_400_000, source: 'measured' })).toBe(120)
    expect(remainingSeconds({ bytesPerSecond: 20_000, received: FIRST_VIEW_BYTES + 1, source: 'measured' })).toBe(0)
    expect(describeWait(120)).toBe('about 2 minutes')
    expect(describeWait(44)).toBe('about 40 seconds')
    expect(describeWait(70)).toBe('about a minute')
    expect(describeWait(5)).toBe('a few seconds')
    expect(describeSpeed(41_500)).toBe('42 KB/s')
    expect(describeSpeed(2_500_000)).toBe('2.5 MB/s')
  })
})

describe('light mode', () => {
  it('switches itself on only for a device that says it is weak', () => {
    expect(looksLowEnd({ cores: 2 })).toBe(true)
    expect(looksLowEnd({ memoryGB: 2 })).toBe(true)
    expect(looksLowEnd({ saveData: true })).toBe(true)
    expect(looksLowEnd({ cores: 8, memoryGB: 8 })).toBe(false)
    expect(looksLowEnd({})).toBe(false) // A browser that does not say is left at full quality
  })

  it('remembers the reader’s choice and marks the page for the stylesheet', () => {
    lite.set(true)
    expect(lite.on).toBe(true)
    expect(lite.automatic).toBe(false)
    expect(document.documentElement.classList.contains('lite')).toBe(true)
    expect(localStorage.getItem('cascadelens.lite')).toBe('on')
    lite.set(false)
    expect(document.documentElement.classList.contains('lite')).toBe(false)
  })
})
