import { useSyncExternalStore } from 'react'

// Two helpers for weak links and weak machines.
//
// 1. Connection speed. Some browsers say how fast the link is (navigator.connection); all of them say how many bytes
//    each file took and how long it took (Resource Timing). The app's own files are the measurement, so nothing extra
//    is downloaded to test the link.
// 2. Light mode. Fewer pixels to draw, no decorative motion, and a 3D view that stops redrawing while nothing moves.
//    It changes how the app draws, never what it shows: every figure, layer and evidence label stays the same.

interface NetInfo { effectiveType?: string; downlink?: number; saveData?: boolean }
const net = (): NetInfo | undefined => (typeof navigator !== 'undefined' ? (navigator as Navigator & { connection?: NetInfo }).connection : undefined)

// About what the first map view downloads, compressed: app code (0.8 MB), terrain backdrop tiles (2.9 MB), the first
// radar tiles (1.6 MB) and the data list. Measured on a 1440 x 900 screen on 15 November 2026; used only for the estimate.
export const FIRST_VIEW_BYTES = 5_400_000
// Below this the first view takes more than about half a minute, which is when a reader starts to wonder
export const SLOW_BYTES_PER_S = 90_000

export interface Speed { bytesPerSecond: number; received: number; source: 'measured' | 'browser' }

// The speed seen so far: the bytes that came over the network divided by the time spent waiting for them.
// Cached files count as nothing, so a second visit is not mistaken for a slow one.
export function measuredSpeed(entries: PerformanceEntryList = performance.getEntriesByType('resource')): Speed | null {
  let bytes = 0, ms = 0, end = 0
  // Files download side by side, so the wall time from the first start to the last finish is the honest divisor
  let start = Infinity
  for (const e of entries as PerformanceResourceTiming[]) {
    if (!e.transferSize || e.transferSize < 300) continue // From the cache, or a header-only answer
    bytes += e.transferSize
    start = Math.min(start, e.startTime)
    end = Math.max(end, e.responseEnd)
  }
  ms = end - start
  if (bytes < 60_000 || !(ms > 400)) return null // Too little to judge
  return { bytesPerSecond: bytes / (ms / 1000), received: bytes, source: 'measured' }
}

// What the browser itself reports, when it reports anything (Chrome, Edge and Android; not Firefox or Safari)
export function browserSpeed(n: NetInfo | undefined = net()): Speed | null {
  if (!n) return null
  if (n.effectiveType === 'slow-2g') return { bytesPerSecond: 6_000, received: 0, source: 'browser' }
  if (n.effectiveType === '2g') return { bytesPerSecond: 30_000, received: 0, source: 'browser' }
  if (typeof n.downlink === 'number' && n.downlink > 0) return { bytesPerSecond: (n.downlink * 1_000_000) / 8, received: 0, source: 'browser' }
  return null
}

// "about 2 minutes", "about 40 seconds"; never more precise than the measurement deserves
export function describeWait(seconds: number): string {
  if (seconds < 20) return 'a few seconds'
  if (seconds < 60) return `about ${Math.round(seconds / 10) * 10} seconds`
  const min = Math.round(seconds / 60)
  return min <= 1 ? 'about a minute' : `about ${min} minutes`
}

export function describeSpeed(bytesPerSecond: number): string {
  return bytesPerSecond >= 1_000_000 ? `${(bytesPerSecond / 1_000_000).toFixed(1)} MB/s` : `${Math.max(1, Math.round(bytesPerSecond / 1000))} KB/s`
}

// Seconds still to wait for the first view at this speed, or null when it is done or cannot be told
export function remainingSeconds(speed: Speed, total = FIRST_VIEW_BYTES): number {
  return Math.max(0, total - speed.received) / Math.max(1, speed.bytesPerSecond)
}

// --- Light mode -------------------------------------------------------------------------------------------------

const KEY = 'cascadelens.lite'
type Choice = 'on' | 'off' | null

function savedChoice(): Choice {
  try {
    const asked = new URLSearchParams(window.location.search).get('lite')
    if (asked === '1') return 'on'
    if (asked === '0') return 'off'
    const v = localStorage.getItem(KEY)
    return v === 'on' || v === 'off' ? v : null
  } catch {
    return null
  }
}

export interface DeviceHints { cores?: number; memoryGB?: number; saveData?: boolean }
export function deviceHints(): DeviceHints {
  const n = typeof navigator !== 'undefined' ? (navigator as Navigator & { deviceMemory?: number }) : undefined
  return { cores: n?.hardwareConcurrency, memoryGB: n?.deviceMemory, saveData: net()?.saveData }
}

// A machine that will struggle to draw the map and 3D smoothly: two cores or fewer, 2 GB of memory or less,
// or a reader who asked the browser to save data. Browsers that do not say leave this off.
export function looksLowEnd(h: DeviceHints = deviceHints()): boolean {
  return Boolean(h.saveData) || (h.cores !== undefined && h.cores > 0 && h.cores <= 2) || (h.memoryGB !== undefined && h.memoryGB > 0 && h.memoryGB <= 2)
}

let choice: Choice = typeof window === 'undefined' ? null : savedChoice()
const auto = typeof window === 'undefined' ? false : looksLowEnd()
const listeners = new Set<() => void>()

export const lite = {
  /** Light mode is on, by the reader's choice or because the device looked weak */
  get on(): boolean { return choice ? choice === 'on' : auto },
  /** It is on only because the device looked weak, so the app says why */
  get automatic(): boolean { return !choice && auto },
  set(on: boolean) {
    choice = on ? 'on' : 'off'
    try { localStorage.setItem(KEY, choice) } catch { /* private window */ }
    apply()
    listeners.forEach((f) => f())
  },
  subscribe(f: () => void) { listeners.add(f); return () => { listeners.delete(f) } },
}

// The stylesheet reads this class to drop decorative motion and costly effects
function apply() {
  if (typeof document !== 'undefined') document.documentElement.classList.toggle('lite', lite.on)
}
apply()

export function useLite(): boolean {
  return useSyncExternalStore(lite.subscribe, () => lite.on, () => false)
}

/** Pixel density to draw at: the screen's own, capped lower in light mode, where a sharp picture costs the most */
export function drawRatio(): number {
  const dpr = typeof window === 'undefined' ? 1 : window.devicePixelRatio || 1
  return Math.min(dpr, lite.on ? 1 : 2)
}
