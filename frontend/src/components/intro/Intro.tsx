import { useCallback, useEffect, useRef, useState } from 'react'
import { elapsedMs } from '../../services/simulation'
import { lite } from '../../services/performance'

// The opening screen: the mark, a counter that follows the real loading, then "Ready" and a fade into the map.
// It never holds the reader back: a click or a key skips it, it is shown once per browser tab, and it stays away
// for anyone who asked their system for less motion. `?intro=1` forces it and `?intro=0` turns it off.

const KEY = 'cascadelens.intro.seen'
const MIN_MS = 1900 // Long enough to read the counter, even when everything is cached
const MAX_MS = 9000 // The map may never report ready, for example without WebGL
const READY_MS = 750
const LEAVE_MS = 700

export function introWanted(): boolean {
  try {
    if (import.meta.env.MODE === 'test') return false
    const asked = new URLSearchParams(window.location.search).get('intro')
    if (asked === '1') return true
    if (asked === '0') return false
    if (navigator.webdriver) return false // Automated browsers test the app, not its opening
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false
    if (lite.on) return false // A weak device gets to the map sooner
    return sessionStorage.getItem(KEY) !== '1'
  } catch {
    return false
  }
}

type Phase = 'counting' | 'ready' | 'leaving'

const CHEVRONS = [0, 1, 2, 3, 4, 5, 6]
const RING = 2 * Math.PI * 20

export function Intro({ progress, onDone }: { progress: number; onDone: () => void }) {
  const [shown, setShown] = useState(0)
  const [phase, setPhase] = useState<Phase>('counting')
  const real = useRef(progress)
  real.current = progress

  useEffect(() => {
    try { sessionStorage.setItem(KEY, '1') } catch { /* private window */ }
    const start = performance.now()
    let value = 0
    let frame = requestAnimationFrame(function tick(now) {
      const t = elapsedMs(now, start)
      const target = t >= MAX_MS ? 100 : Math.min(real.current, t / MIN_MS) * 100
      value = Math.min(100, value + Math.max(0.4, (target - value) * 0.12))
      if (value > target) value = target
      setShown(value)
      if (value >= 100) setPhase((p) => (p === 'counting' ? 'ready' : p))
      else frame = requestAnimationFrame(tick)
    })
    return () => cancelAnimationFrame(frame)
  }, [])

  useEffect(() => {
    document.documentElement.classList.toggle('intro-hold', phase !== 'leaving')
    if (phase === 'counting') return
    const timer = window.setTimeout(phase === 'ready' ? () => setPhase('leaving') : onDone, phase === 'ready' ? READY_MS : LEAVE_MS)
    return () => window.clearTimeout(timer)
  }, [phase, onDone])
  useEffect(() => () => document.documentElement.classList.remove('intro-hold'), [])

  const skip = useCallback(() => setPhase('leaving'), [])
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape' || e.key === 'Enter' || e.key === ' ') skip() }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [skip])

  const n = Math.round(shown)
  return (
    <div className={`intro ${phase}`} onClick={skip}>
      <p className="sr-only" role="status">CascadeLens is loading</p>
      <p className="intro-word" aria-hidden="true">CascadeLens</p>
      <div className="intro-centre" aria-hidden="true">
        <svg className="intro-mark" viewBox="0 0 120 120">
          <defs>
            <linearGradient id="intro-gold" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#6b5226" /><stop offset=".55" stopColor="#cea154" /><stop offset="1" stopColor="#f0d9a0" />
            </linearGradient>
            <clipPath id="intro-lens"><circle cx="52" cy="52" r="41" /></clipPath>
          </defs>
          <g fill="none" stroke="url(#intro-gold)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="52" cy="52" r="45" />
            <path d="M85 85 110 110" strokeWidth="5" />
            <g clipPath="url(#intro-lens)">
              {CHEVRONS.map((k) => <path key={k} className="intro-line" style={{ animationDelay: `${k * 0.16}s` }} d={`M-12 ${78 + k * 10} L52 ${16 + k * 10} L116 ${78 + k * 10}`} />)}
            </g>
          </g>
        </svg>
        <div className="intro-count">
          <svg viewBox="0 0 44 44">
            <circle cx="22" cy="22" r="20" />
            <circle className="arc" cx="22" cy="22" r="20" strokeDasharray={`${(shown / 100) * RING} ${RING}`} transform="rotate(-90 22 22)" />
          </svg>
          <span className="intro-number">{n}</span>
          <span className="intro-ready">Ready</span>
        </div>
      </div>
      <p className="intro-hint" aria-hidden="true">Radar evidence for mountain hazards<span>Click anywhere to skip</span></p>
    </div>
  )
}
