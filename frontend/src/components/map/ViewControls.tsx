import { useCallback, useEffect, useState } from 'react'
import type { Map as MlMap } from 'maplibre-gl'
import type { Bounds, Layer } from '../../types/manifest'
import { canPan, centreToSlider, clampCentre, latOf, lngOf, mercX, mercY, sliderToCentre, zoomCeiling } from '../../services/viewMath'

// Sliders for moving the flat map, beside dragging, scrolling, pinching and the keyboard. They keep to the study area, so
// "Whole area" always brings the view back.
// Story steps, bookmarks and Simulate still move the map themselves, and the sliders follow them on `moveend`.

export const FIT_PADDING = 30
const PAN_STEPS = 1000

interface ViewState { zoom: number; fit: number; max: number; x: number; y: number; panX: boolean; panY: boolean }

// The envelope in Mercator units. y grows southwards, so north is the low edge.
const box = (e: Bounds) => ({ x0: mercX(e[0]), x1: mercX(e[2]), y0: mercY(e[3]), y1: mercY(e[1]) })

function spans(map: MlMap) {
  const b = map.getBounds()
  return { w: mercX(b.getEast()) - mercX(b.getWest()), h: mercY(b.getSouth()) - mercY(b.getNorth()) }
}

export function fitZoomOf(map: MlMap, envelope: Bounds) {
  return map.cameraForBounds(envelope as [number, number, number, number], { padding: FIT_PADDING })?.zoom ?? map.getZoom()
}

function deepest(layer: Layer | undefined) {
  const z = layer?.sources.map((s) => s.tiles.maxzoom).filter((v) => Number.isFinite(v)) ?? []
  return z.length ? Math.max(...z) : undefined
}

function read(map: MlMap, envelope: Bounds, layer: Layer | undefined): ViewState {
  const fit = fitZoomOf(map, envelope)
  const { x0, x1, y0, y1 } = box(envelope)
  const { w, h } = spans(map)
  const c = map.getCenter()
  return {
    zoom: map.getZoom(), fit, max: zoomCeiling(fit, deepest(layer)),
    x: centreToSlider(mercX(c.lng), x0, x1, w),
    y: 1 - centreToSlider(mercY(c.lat), y0, y1, h), // The slider runs south to north, Mercator y north to south
    panX: canPan(x0, x1, w), panY: canPan(y0, y1, h),
  }
}

export function ViewControls({ map, envelope, layer }: { map: MlMap | null; envelope: Bounds; layer: Layer | undefined }) {
  const [v, setV] = useState<ViewState | null>(null)
  const [open] = useState(() => typeof window.matchMedia !== 'function' || !window.matchMedia('(max-width: 980px)').matches)

  const sync = useCallback(() => { if (map) setV(read(map, envelope, layer)) }, [map, envelope, layer])
  useEffect(() => {
    if (!map) return
    sync()
    map.on('moveend', sync)
    map.on('resize', sync)
    return () => { map.off('moveend', sync); map.off('resize', sync) }
  }, [map, sync])

  if (!map || !v) return null

  const go = (camera: { center?: [number, number]; zoom?: number }) => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) map.easeTo({ ...camera, duration: 0 })
    else map.jumpTo(camera)
  }
  const { x0, x1, y0, y1 } = box(envelope)

  const zoomTo = (zoom: number) => {
    // The view's size at the new zoom, so the centre can be clamped before the move and never shows ground outside the area
    const k = 2 ** (map.getZoom() - zoom)
    const { w, h } = spans(map)
    const c = map.getCenter()
    const cx = canPan(x0, x1, w * k) ? clampCentre(mercX(c.lng), x0, x1, w * k) : (x0 + x1) / 2
    const cy = canPan(y0, y1, h * k) ? clampCentre(mercY(c.lat), y0, y1, h * k) : (y0 + y1) / 2
    go({ zoom, center: [lngOf(cx), latOf(cy)] })
  }
  const panX = (t: number) => {
    const c = map.getCenter()
    go({ center: [lngOf(sliderToCentre(t, x0, x1, spans(map).w)), c.lat] })
  }
  const panY = (t: number) => {
    const c = map.getCenter()
    go({ center: [c.lng, latOf(sliderToCentre(1 - t, y0, y1, spans(map).h))] })
  }
  const whole = () => go({ zoom: v.fit, center: [lngOf((x0 + x1) / 2), latOf((y0 + y1) / 2)] })

  const level = v.max > v.fit ? Math.round(((Math.min(v.max, Math.max(v.fit, v.zoom)) - v.fit) / (v.max - v.fit)) * 100) : 0
  return (
    <details className="view-controls" open={open} data-testid="view-controls">
      <summary>View</summary>
      <label className="slider">Zoom <span>{level === 0 ? 'Whole study area' : `${level}%`}</span>
        <input type="range" aria-label="Zoom, from the whole study area to the most detailed tiles" min={v.fit} max={Math.max(v.max, v.fit + 0.01)} step="any"
          value={Math.min(v.max, Math.max(v.fit, v.zoom))} disabled={v.max <= v.fit} onChange={(e) => zoomTo(Number(e.target.value))} />
      </label>
      <label className="slider">West ↔ East
        <input type="range" aria-label="Move the view west or east" min={0} max={PAN_STEPS} step={1} value={Math.round(v.x * PAN_STEPS)} disabled={!v.panX}
          onChange={(e) => panX(Number(e.target.value) / PAN_STEPS)} />
      </label>
      <label className="slider">South ↔ North
        <input type="range" aria-label="Move the view south or north" min={0} max={PAN_STEPS} step={1} value={Math.round(v.y * PAN_STEPS)} disabled={!v.panY}
          onChange={(e) => panY(Number(e.target.value) / PAN_STEPS)} />
      </label>
      {!v.panX && !v.panY && <p className="muted small">The whole area is in view, so there is nothing to move to. Zoom in first.</p>}
      <button className="ghost" onClick={whole}>Whole area</button>
    </details>
  )
}
