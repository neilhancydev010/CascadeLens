import { useEffect, useRef, useState } from 'react'

// Side panels get out of the way while the reader drags, zooms or turns the 3D model,
// and slide back when the pointer reaches the left or right edge of the screen (or a panel gets keyboard focus).
// Only on large screens with a mouse; phones keep their bottom sheets.
// Dragging and zooming the map (MapView.tsx) leave the panels where they are: only the reader's own choice hides them.
// The 3D model still turns and zooms.

const EDGE_PX = 24
const DRAG_PX = 6
const matches = (q: string) => typeof window.matchMedia === 'function' && Boolean(window.matchMedia(q)?.matches)
const desktop = () => matches('(min-width: 981px) and (hover: hover) and (pointer: fine)')
const wide = () => matches('(min-width: 981px)')

// `tuckLeft` starts a mode with the controls panel already away: its tab at the screen edge, or keyboard focus, brings it back.
export function useAutoHidePanels(resetKey: string, tuckLeft = false) {
  const [hideLeft, setHideLeft] = useState(false)
  const [hideRight, setHideRight] = useState(false)
  const down = useRef<{ x: number; y: number } | null>(null)

  // A new mode brings its panels back
  useEffect(() => { setHideLeft(tuckLeft && wide()); setHideRight(false) }, [resetKey, tuckLeft])

  useEffect(() => {
    const onData = (t: EventTarget | null) => t instanceof HTMLCanvasElement && Boolean(t.closest('.terrain-canvas'))
    const hide = () => { if (desktop()) { setHideLeft(true); setHideRight(true) } }
    const pointerDown = (e: PointerEvent) => { down.current = onData(e.target) ? { x: e.clientX, y: e.clientY } : null }
    const pointerMove = (e: PointerEvent) => {
      const d = down.current
      if (d && e.buttons && Math.hypot(e.clientX - d.x, e.clientY - d.y) > DRAG_PX) { hide(); down.current = null }
      if (!e.buttons && desktop()) {
        if (e.clientX <= EDGE_PX) setHideLeft(false)
        if (e.clientX >= window.innerWidth - EDGE_PX) setHideRight(false)
      }
    }
    const pointerUp = () => { down.current = null }
    const wheel = (e: WheelEvent) => { if (onData(e.target)) hide() }
    const focus = (e: FocusEvent) => {
      const el = e.target as HTMLElement | null
      if (el?.closest?.('.left')) setHideLeft(false)
      if (el?.closest?.('.right, .compare-dock, .sim-dock, .terrain-panel')) setHideRight(false)
    }
    window.addEventListener('pointerdown', pointerDown, true)
    window.addEventListener('pointermove', pointerMove, true)
    window.addEventListener('pointerup', pointerUp, true)
    window.addEventListener('wheel', wheel, { capture: true, passive: true })
    window.addEventListener('focusin', focus)
    return () => {
      window.removeEventListener('pointerdown', pointerDown, true)
      window.removeEventListener('pointermove', pointerMove, true)
      window.removeEventListener('pointerup', pointerUp, true)
      window.removeEventListener('wheel', wheel, { capture: true } as EventListenerOptions)
      window.removeEventListener('focusin', focus)
    }
  }, [])

  return { hideLeft, hideRight, showLeft: () => setHideLeft(false), showRight: () => setHideRight(false) }
}
