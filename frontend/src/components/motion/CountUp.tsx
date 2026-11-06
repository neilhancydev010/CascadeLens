import { useEffect, useRef, useState } from 'react'

// A number that counts up to its value when it first appears, and glides when the value changes.
// Shows the final value at once when the reader has asked the system for less motion.

const calm = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

export function CountUp({ value, format, ms = 900 }: { value: number; format: (v: number) => string; ms?: number }) {
  const [shown, setShown] = useState(() => (calm() ? value : 0))
  const from = useRef(shown)
  useEffect(() => {
    if (calm()) { setShown(value); from.current = value; return }
    const start = performance.now()
    const a = from.current
    let frame = requestAnimationFrame(function tick(now) {
      const k = Math.min(1, (now - start) / ms)
      const e = 1 - Math.pow(1 - k, 3)
      const v = a + (value - a) * e
      setShown(v)
      from.current = v
      if (k < 1) frame = requestAnimationFrame(tick)
    })
    return () => cancelAnimationFrame(frame)
  }, [value, ms])
  return <span className="count-up">{format(shown)}</span>
}
