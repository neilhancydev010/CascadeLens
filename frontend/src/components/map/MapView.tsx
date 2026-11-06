import { useEffect, useRef, useState } from 'react'
import { Map as MlMap, Marker, NavigationControl, ScaleControl, setWorkerUrl, type GeoJSONSource, type LngLatBoundsLike, type StyleSpecification } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import type { Bounds, GranuleRecord, Layer } from '../../types/manifest'
import { assetUrl } from '../../services/manifest'
import type { SimView } from '../../services/simulation'

// MapLibre derives the worker path from its own module URL, which Vite's bundling moves.
setWorkerUrl(new URL(workerUrl, document.baseURI).href)

export interface MapStatus { state: 'loading' | 'ready' | 'error'; message?: string }

interface Props {
  envelope: Bounds
  terrain: Layer | undefined
  showTerrain: boolean
  active: Layer | undefined
  overlay: Layer | undefined
  showMask: boolean
  opacity: number
  references: Layer[]
  footprints: GranuleRecord[]
  point: [number, number] | null
  focus: { bounds: Bounds; nonce: number } | null
  sim: SimView | null
  onPoint: (p: [number, number]) => void
  onStatus: (s: MapStatus) => void
  onCoverage: (covered: boolean) => void
}

// No glyphs and no remote sources: the map must work with the network off. Place names are DOM markers for the same reason.
const STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [
    { id: 'bg', type: 'background', paint: { 'background-color': '#0f1518' } },
    { id: 'anchor-base', type: 'background', layout: { visibility: 'none' } },
    { id: 'anchor-analysis', type: 'background', layout: { visibility: 'none' } },
    { id: 'anchor-overlay', type: 'background', layout: { visibility: 'none' } },
    { id: 'anchor-refs', type: 'background', layout: { visibility: 'none' } },
  ],
}

const empty = { type: 'FeatureCollection' as const, features: [] }

function clear(map: MlMap, prefix: string) {
  for (const l of map.getStyle().layers ?? []) if (l.id.startsWith(prefix)) map.removeLayer(l.id)
  for (const s of Object.keys(map.getStyle().sources ?? {})) if (s.startsWith(prefix)) map.removeSource(s)
}

function addRaster(map: MlMap, prefix: string, layer: Layer, opacity: number, before: string, tilesOf: (s: Layer['sources'][number]) => string | undefined = (s) => s.tiles.url) {
  // Reversed so the first frame draws on top, matching which frame the inspector reports in an overlap.
  ;[...layer.sources].reverse().forEach((s, i) => {
    const url = tilesOf(s)
    if (!url) return
    const id = `${prefix}${i}`
    map.addSource(id, { type: 'raster', tiles: [assetUrl(url)], tileSize: 256, minzoom: s.tiles.minzoom, maxzoom: s.tiles.maxzoom, bounds: s.bounds })
    map.addLayer({ id, type: 'raster', source: id, paint: { 'raster-opacity': opacity, 'raster-resampling': 'nearest', 'raster-fade-duration': 0 } }, before)
  })
}

function addReference(map: MlMap, l: Layer) {
  const id = `ref-${l.id}`
  if (l.sources.length) {
    const s = l.sources[0]
    map.addSource(id, { type: 'raster', tiles: [assetUrl(s.tiles.url)], tileSize: 256, minzoom: s.tiles.minzoom, maxzoom: s.tiles.maxzoom, bounds: s.bounds })
    map.addLayer({ id, type: 'raster', source: id, paint: { 'raster-resampling': 'nearest', 'raster-fade-duration': 0 } }, 'anchor-refs')
    return
  }
  const v = l.vector!
  if (v.type === 'label') return
  map.addSource(id, { type: 'geojson', data: assetUrl(v.url) })
  const base = { id, source: id }
  if (v.type === 'fill') {
    map.addLayer({ ...base, type: 'fill', paint: { 'fill-color': v.color!, 'fill-opacity': v.opacity ?? 0.5, 'fill-outline-color': v.color! } })
  } else if (v.type === 'line') {
    map.addLayer({ ...base, type: 'line', paint: { 'line-color': v.color!, 'line-opacity': v.opacity ?? 0.8, 'line-width': 1.4, ...(v.dash ? { 'line-dasharray': [3, 2] } : {}) } })
  } else {
    map.addLayer({ ...base, type: 'circle', paint: { 'circle-color': v.color!, 'circle-opacity': v.opacity ?? 0.8, 'circle-radius': v.radius ?? 2 } })
  }
}

export function MapView({ envelope, terrain, showTerrain, active, overlay, showMask, opacity, references, footprints, point, focus, sim, onPoint, onStatus, onCoverage }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MlMap | null>(null)
  const pointMarker = useRef<Marker | null>(null)
  const simHead = useRef<Marker | null>(null)
  const labels = useRef<Marker[]>([])
  const [ready, setReady] = useState(false)
  const envelopeRef = useRef(envelope) // The map lives for the whole session: rebuilding it mid-render races its effects
  const onPointRef = useRef(onPoint)
  const onStatusRef = useRef(onStatus)
  const onCoverageRef = useRef(onCoverage)
  onPointRef.current = onPoint
  onStatusRef.current = onStatus
  onCoverageRef.current = onCoverage

  useEffect(() => {
    if (!host.current) return
    const envelope = envelopeRef.current
    // MapLibre fires these for every tile. Passing on only real changes stops the whole page redrawing each time.
    let last: MapStatus | undefined
    const report = (s: MapStatus) => {
      if (s.state === last?.state && s.message === last?.message) return
      if (s.state === 'ready' && last?.state === 'error') return // A failed layer must keep its warning: idle only means loading stopped
      last = s
      onStatusRef.current(s)
    }
    const map = new MlMap({ container: host.current, style: STYLE, bounds: envelope as LngLatBoundsLike, fitBoundsOptions: { padding: 30 }, attributionControl: false, dragRotate: false, pitchWithRotate: false, renderWorldCopies: false })
    mapRef.current = map
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-left')
    map.on('load', () => {
      const [w, s, e, n] = envelope
      map.addSource('study-envelope', { type: 'geojson', data: { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } } })
      map.addLayer({ id: 'study-envelope', type: 'line', source: 'study-envelope', paint: { 'line-color': '#e7c66b', 'line-width': 1, 'line-dasharray': [4, 3], 'line-opacity': 0.75 } })
      map.addSource('footprints', { type: 'geojson', data: empty })
      map.addLayer({ id: 'footprints', type: 'line', source: 'footprints', paint: { 'line-color': '#7fd1c7', 'line-width': 1.5, 'line-opacity': 0.85 } })
      setReady(true)
      report({ state: 'ready' })
    })
    map.on('click', (e) => onPointRef.current([e.lngLat.lng, e.lngLat.lat]))
    map.on('dataloading', () => report({ state: 'loading' }))
    map.on('idle', () => report({ state: 'ready' }))
    map.on('error', (e) => {
      const err = e.error as Error & { status?: number }
      if (err?.status === 404) return // Sparse pyramids skip empty tiles
      const source = (e as unknown as { sourceId?: string }).sourceId
      report({ state: 'error', message: source ? `Could not load map source ${source}. ${err?.message ?? ''}` : (err?.message ?? 'Map error') })
    })
    if (import.meta.env.DEV) (window as unknown as { __clMap: MlMap }).__clMap = map
    return () => { map.remove(); mapRef.current = null; setReady(false) }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    clear(map, 'base-')
    if (terrain && showTerrain) addRaster(map, 'base-', terrain, 1, 'anchor-base')
  }, [ready, terrain, showTerrain])

  const activeIsBase = active?.id === terrain?.id
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    clear(map, 'active-')
    if (active && !activeIsBase) addRaster(map, 'active-', active, opacity, 'anchor-analysis')
    // eslint-disable-next-line react-hooks/exhaustive-deps -- opacity is applied in place below, without reloading tiles
  }, [ready, active, activeIsBase])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    for (const l of map.getStyle().layers ?? []) if (l.id.startsWith('active-')) map.setPaintProperty(l.id, 'raster-opacity', opacity)
  }, [ready, opacity])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const check = () => {
      const b = map.getBounds()
      const outside = (s: Bounds) => s[2] < b.getWest() || s[0] > b.getEast() || s[3] < b.getSouth() || s[1] > b.getNorth()
      onCoverageRef.current(!active?.sources.length || active.sources.some((s) => !outside(s.bounds)))
    }
    check()
    map.on('moveend', check)
    return () => { map.off('moveend', check) }
  }, [ready, active])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    clear(map, 'overlay-')
    if (overlay) addRaster(map, 'overlay-q', overlay, 0.8, 'anchor-overlay')
    if (active && showMask) addRaster(map, 'overlay-m', active, 0.9, 'anchor-overlay', (s) => s.maskTiles)
  }, [ready, overlay, active, showMask])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const wanted = new Set(references.map((r) => `ref-${r.id}`))
    for (const l of map.getStyle().layers ?? []) if (l.id.startsWith('ref-') && !wanted.has(l.id)) map.removeLayer(l.id)
    for (const s of Object.keys(map.getStyle().sources ?? {})) if (s.startsWith('ref-') && !wanted.has(s)) map.removeSource(s)
    for (const r of references) if (!map.getLayer(`ref-${r.id}`)) addReference(map, r)
    if (map.getLayer('footprints')) map.moveLayer('footprints')
    if (map.getLayer('study-envelope')) map.moveLayer('study-envelope')
  }, [ready, references])

  // One source and a filter on each layer: moving a slider only changes the filters, so no geometry is sent again.
  const simData = sim?.data
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    clear(map, 'sim-')
    if (!simData) return
    const source = 'sim-data'
    map.addSource(source, { type: 'geojson', data: simData.features })
    map.addLayer({ id: 'sim-route', type: 'line', source, filter: ['==', ['get', 'k'], 'c'], layout: { 'line-cap': 'round' }, paint: { 'line-color': '#fff', 'line-opacity': 0.35, 'line-width': 2 } })
    map.addLayer({ id: 'sim-done', type: 'line', source, layout: { 'line-cap': 'round' }, paint: { 'line-color': '#5fe0c9', 'line-width': 4 } })
    map.addLayer({ id: 'sim-lines', type: 'line', source, paint: { 'line-color': '#ff7f66', 'line-width': 2 } })
    map.addLayer({ id: 'sim-points', type: 'circle', source, paint: { 'circle-color': '#ff7f66', 'circle-stroke-color': '#fff', 'circle-stroke-width': ['case', ['==', ['get', 'k'], 'p'], 1.5, 0], 'circle-radius': ['case', ['==', ['get', 'k'], 'p'], 5, 2.5] } })
  }, [ready, simData])

  const simMode = sim?.mode
  const simKm = sim?.km
  const simRise = sim?.rise
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map?.getLayer('sim-done') || simKm === undefined) return
    const kinds = (list: string[]) => ['in', ['get', 'k'], ['literal', list]] as const
    const reached = ['<=', ['get', 'km'], simKm] as const
    const low = simMode === 'whatif' ? [['<=', ['get', 'h'], simRise]] : []
    const filter = (list: string[]) => ['all', kinds(list), reached, ...low] as never
    map.setFilter('sim-done', ['all', kinds(['c']), reached] as never)
    map.setFilter('sim-lines', filter(simMode === 'whatif' ? ['r'] : ['a']))
    map.setFilter('sim-points', filter(['b', 'p']))
  }, [ready, simData, simMode, simKm, simRise])

  useEffect(() => {
    const map = mapRef.current
    const at = simData && simKm !== undefined ? simData.path[simKm] : undefined
    if (!ready || !map || !at) { simHead.current?.remove(); simHead.current = null; return }
    if (!simHead.current) {
      const el = document.createElement('div')
      el.className = 'sim-head'
      simHead.current = new Marker({ element: el }).setLngLat([at[0], at[1]]).addTo(map)
    }
    simHead.current.setLngLat([at[0], at[1]])
  }, [ready, simData, simKm])

  const places = references.find((r) => r.vector?.type === 'label')
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !places) return
    let stale = false
    fetch(assetUrl(places.vector!.url))
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then((fc: { features: { geometry: { coordinates: [number, number] }; properties: { label: string } }[] }) => {
        if (stale) return
        labels.current = fc.features.map((f) => {
          const el = document.createElement('span')
          el.className = 'place-label'
          el.textContent = f.properties.label
          return new Marker({ element: el, anchor: 'left', offset: [5, 0] }).setLngLat(f.geometry.coordinates).addTo(map)
        })
      })
      .catch((e) => onStatusRef.current({ state: 'error', message: `Reference layer unavailable: ${places.name}. ${e.message}` }))
    return () => {
      stale = true
      labels.current.forEach((m) => m.remove())
      labels.current = []
    }
  }, [ready, places])

  useEffect(() => {
    const src = mapRef.current?.getSource('footprints') as GeoJSONSource | undefined
    if (!ready || !src) return
    src.setData({ type: 'FeatureCollection', features: footprints.filter((g) => g.geometry).map((g) => ({ type: 'Feature', properties: { frame: g.frame }, geometry: g.geometry })) } as Parameters<GeoJSONSource['setData']>[0])
  }, [ready, footprints])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    pointMarker.current?.remove()
    pointMarker.current = null
    if (!point) return
    const el = document.createElement('div')
    el.className = 'point-marker'
    pointMarker.current = new Marker({ element: el }).setLngLat(point).addTo(map)
  }, [point])

  useEffect(() => {
    if (!focus || !ready) return
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    // On a phone the story is a bottom sheet over the map, so frame the bookmark in the part still visible.
    const phone = window.matchMedia('(max-width: 980px)').matches
    // On a large screen the story card floats over the bottom of the map, and the left panel over its left side.
    const sheet = document.querySelector('.story')?.getBoundingClientRect()
    const covered = sheet && sheet.top > 100 ? window.innerHeight - sheet.top : 0
    const left = !phone && document.querySelector('.app:not(.hide-left) .left') ? 350 : 0
    const dock = !phone && document.querySelector('.app:not(.hide-right) .compare-dock') ? 450 : 0
    const panels = !phone && document.querySelector('.sim-panel') // The whole path should clear the side panels and the top bar
    mapRef.current?.fitBounds(focus.bounds as LngLatBoundsLike, { padding: panels ? { top: 100, left: 360, right: 400, bottom: 40 } : { top: 90, left: 40 + left, right: 60 + dock, bottom: 30 + covered }, duration: calm ? 0 : 900 })
  }, [focus, ready])

  return <div ref={host} className="map" role="application" aria-label="Study area map. Click to inspect a location." data-testid="map" />
}
