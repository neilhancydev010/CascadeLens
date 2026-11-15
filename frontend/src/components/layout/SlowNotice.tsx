import { useEffect, useState } from 'react'
import { browserSpeed, describeSpeed, describeWait, lite, measuredSpeed, remainingSeconds, SLOW_BYTES_PER_S, useLite, type Speed } from '../../services/performance'

// A warning while the map is still loading on a slow link: how fast the link is, about how long is left,
// and a way to make the app lighter. It goes away by itself once the map is ready, or when the reader hides it.

const EARLY_MS = 3_000 // A link the browser already calls slow is said early
const LATE_MS = 10_000 // Any link is said once the map has kept the reader waiting this long

export function SlowNotice({ loading }: { loading: boolean }) {
  const [speed, setSpeed] = useState<Speed | null>(null)
  const [late, setLate] = useState(false)
  const [hidden, setHidden] = useState(false)
  const on = useLite()

  useEffect(() => {
    if (!loading) return
    const tick = () => {
      setSpeed(measuredSpeed() ?? browserSpeed())
      setLate(performance.now() > LATE_MS)
    }
    tick()
    const timer = window.setInterval(tick, 2000)
    return () => window.clearInterval(timer)
  }, [loading])

  const slow = speed !== null && speed.bytesPerSecond < SLOW_BYTES_PER_S
  const shown = loading && !hidden && ((slow && performance.now() > EARLY_MS) || late)
  if (!shown) return null
  const left = speed ? remainingSeconds(speed) : null
  return (
    <div className="slow-notice" role="status">
      <span className="slow-icon" aria-hidden="true">!</span>
      <p>
        <strong>{slow ? 'Slow connection' : 'Taking longer than usual'}</strong>
        {speed && slow ? ` (about ${describeSpeed(speed.bytesPerSecond)})` : ''}
        {': '}{left !== null && left >= 20 ? `the map may need ${describeWait(left)} more to load.` : 'the map is still loading.'}
      </p>
      <span className="slow-actions">
        {!on && <button className="link" onClick={() => lite.set(true)}>Use light mode</button>}
        <button className="link" onClick={() => setHidden(true)}>Hide</button>
      </span>
    </div>
  )
}

// Said once, when light mode switched itself on for a low-powered device, so the reader knows why and can undo it
export function LiteNotice() {
  const on = useLite()
  const [hidden, setHidden] = useState(() => { try { return sessionStorage.getItem('cascadelens.lite.told') === '1' } catch { return false } })
  if (!on || !lite.automatic || hidden) return null
  const hide = () => { setHidden(true); try { sessionStorage.setItem('cascadelens.lite.told', '1') } catch { /* private window */ } }
  return (
    <div className="slow-notice lite-notice" role="status">
      <span className="slow-icon" aria-hidden="true">i</span>
      <p title="The map and 3D are drawn at a lighter setting and decorative motion is off. All data and labels are the same."><strong>Light mode is on</strong> because this device looks low-powered. The data shown is the same.</p>
      <span className="slow-actions">
        <button className="link" onClick={() => { lite.set(false); hide() }}>Use full quality</button>
        <button className="link" onClick={hide}>OK</button>
      </span>
    </div>
  )
}

// The switch kept in the map footer, so light mode can be turned on or off at any time
export function LiteToggle() {
  const on = useLite()
  return <button className="link lite-toggle" aria-pressed={on} onClick={() => lite.set(!on)} title="Draws the map and 3D more lightly for slow or older devices. The data shown does not change.">Light mode: {on ? 'on' : 'off'}</button>
}
