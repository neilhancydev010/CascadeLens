import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { assetUrl, formatDate } from '../../services/manifest'
import { elapsedMs } from '../../services/simulation'
import type { EvidenceClass } from '../../services/evidence'
import { EvidenceTag } from '../explanations/EvidenceTag'
import { buildBlock, strataTexture, type Built } from './block3d'

// A block model of the whole Rasuwa–Bhote Koshi–Trishuli corridor: NASADEM heights with UNOSAT maps, OSM rivers and NASA
// radar layers (NISAR stability and backscatter, OPERA Sentinel-1 change) draped on top, and arrows for the way each NISAR
// track looks at the ground.
// Built by processing/scripts/prepare_rasuwa_3d.py. Units in the scene are kilometres; north is towards the back.

interface ModelLayer {
  id: string; file: string; name: string; evidence: EvidenceClass; color: string; on: boolean; group?: 'radar'; attribution?: string; limitations: string[]; maturity?: string
  short?: string; kind?: 'coherence' | 'backscatter' | 'change'; note?: string; legend?: { stops: string[]; min: number; max: number; unit: string }
}
interface ModelTrack { track: number; orbit: string; look: string; losToSensorEastNorth: [number, number]; incidenceDeg5to95?: [number, number]; pair: [string, string]; evidence: EvidenceClass }
interface ModelLabel { name: string; xM: number; yM: number; evidence?: EvidenceClass }
interface ModelSource { name: string; attribution?: string; limitations: string[]; evidence: EvidenceClass }
export interface Model3D {
  name: string
  heights: string
  width: number
  height: number
  spacingM: number
  minM: number
  maxM: number
  drapeSize: [number, number]
  base: string
  baseLayer: ModelSource
  layers: ModelLayer[]
  tracks: ModelTrack[]
  places: ModelLabel[]
  placesLayer: ModelSource
  markers: ModelLabel[]
}

const TRACK_COLOUR: Record<number, string> = { 48: '#5fe0c9', 98: '#c3a6ff' }
const START = new THREE.Vector3(0, 98, 126)
const m = (v: number) => `${Math.round(v).toLocaleString('en-GB')} m`
const compass = (e: number, n: number) => {
  const deg = (Math.atan2(e, n) * 180 / Math.PI + 360) % 360
  return ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west'][Math.round(deg / 45) % 8]
}

function loadImage(url: string) {
  return new Promise<HTMLImageElement>((ok, fail) => {
    const i = new Image()
    i.onload = () => ok(i)
    i.onerror = () => fail(new Error(`Could not load ${url}`))
    i.src = url
  })
}

// Reads a file and reports how much has arrived. `expected` stands in when the server sends no length.
async function fetchBytes(url: string, expected: number, progress: (done: number, total: number) => void) {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`Could not load ${url} (HTTP ${r.status})`)
  const total = Number(r.headers.get('content-length')) || expected
  if (!r.body) { const b = await r.arrayBuffer(); progress(b.byteLength, b.byteLength); return b }
  const reader = r.body.getReader()
  const parts: Uint8Array[] = []
  let done = 0
  for (;;) {
    const { value, done: end } = await reader.read()
    if (end) break
    parts.push(value)
    done += value.byteLength
    progress(done, Math.max(total, done))
  }
  const out = new Uint8Array(done)
  let at = 0
  for (const p of parts) { out.set(p, at); at += p.byteLength }
  return out.buffer
}

async function fetchImage(url: string, progress: (done: number, total: number) => void) {
  const b = await fetchBytes(url, 0, progress)
  const src = URL.createObjectURL(new Blob([b]))
  try { return await loadImage(src) } finally { setTimeout(() => URL.revokeObjectURL(src), 0) }
}

const twice = <T,>(job: () => Promise<T>) => job().catch(() => job())

function label(text: string, colour: string, size = 1) {
  const c = document.createElement('canvas')
  const g = c.getContext('2d')!
  const font = '600 44px Manrope Variable, system-ui, sans-serif'
  g.font = font
  const w = Math.ceil(g.measureText(text).width) + 36
  c.width = w
  c.height = 72
  g.font = font
  g.fillStyle = 'rgba(20, 14, 40, 0.78)'
  g.beginPath()
  g.roundRect(0, 0, w, 72, 18)
  g.fill()
  g.fillStyle = colour
  g.textBaseline = 'middle'
  g.fillText(text, 18, 38)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  // The same size on screen however near the camera is
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false, transparent: true, sizeAttenuation: false }))
  s.center.set(0.5, 0)
  s.scale.set((w / 72) * 0.021 * size, 0.021 * size, 1)
  s.renderOrder = 10
  return s
}

function disposeAll(o: THREE.Object3D) {
  o.traverse((x) => {
    const mesh = x as THREE.Mesh
    mesh.geometry?.dispose()
    const mats = Array.isArray(mesh.material) ? mesh.material : mesh.material ? [mesh.material] : []
    mats.forEach((mt) => { (mt as THREE.MeshBasicMaterial).map?.dispose(); mt.dispose() })
  })
}

export function Rasuwa3D({ url, onExit }: { url: string; onExit: () => void }) {
  const host = useRef<HTMLDivElement>(null)
  const scene = useRef<{ scene: THREE.Scene; camera: THREE.PerspectiveCamera; controls: OrbitControls; strata: THREE.Texture } | null>(null)
  const built = useRef<Built | null>(null)
  const [model, setModel] = useState<Model3D | null>(null)
  const [heights, setHeights] = useState<Float32Array | null>(null)
  const [images, setImages] = useState<Record<string, HTMLImageElement>>({})
  const [failure, setFailure] = useState<string | null>(null)
  const [on, setOn] = useState<Record<string, boolean>>({})
  const [radar, setRadar] = useState<string>('')
  const [tracksOn, setTracksOn] = useState(true)
  const [labelsOn, setLabelsOn] = useState(true)
  const [exag, setExag] = useState(1.5)
  const [spin, setSpin] = useState(false)
  const [missing, setMissing] = useState<string[]>([])
  const [got, setGot] = useState<Record<string, [number, number]>>({})
  const [slow, setSlow] = useState(false)
  const [attempt, setAttempt] = useState(0)

  // The model description, then its heights and the pictures shown at the start. Radar pictures wait until they are picked.
  // Every file counts its bytes so the reader sees progress on a slow connection, and is tried twice before giving up.
  useEffect(() => {
    let live = true
    setModel(null); setHeights(null); setImages({}); setFailure(null); setMissing([]); setGot({}); setSlow(false)
    const fail = (e: Error) => { if (live) setFailure(e.message) }
    const slowTimer = setTimeout(() => { if (live) setSlow(true) }, 25000)
    const track = (id: string) => (done: number, total: number) => { if (live) setGot((g) => ({ ...g, [id]: [done, total] })) }
    fetch(assetUrl(url)).then((r) => { if (!r.ok) throw new Error(`3D model request failed with HTTP ${r.status}`); return r.json() as Promise<Model3D> })
      .then((md) => {
        if (!live) return
        setModel(md)
        setOn(Object.fromEntries(md.layers.filter((l) => l.group !== 'radar').map((l) => [l.id, l.on])))
        const heightsBytes = md.width * md.height * 2
        twice(() => fetchBytes(assetUrl(md.heights), heightsBytes, track('heights')))
          .then((b) => { if (live) setHeights(Float32Array.from(new Int16Array(b))) }).catch(fail)
        ;[['base', md.base], ...md.layers.filter((l) => l.group !== 'radar').map((l) => [l.id, l.file])].forEach(([id, f]) => {
          twice(() => fetchImage(assetUrl(f), track(id)))
            .then((i) => { if (live) setImages((all) => ({ ...all, [id]: i })) })
            .catch((e: Error) => { if (!live) return; if (id === 'base') fail(e); else setMissing((m) => [...m, id]) })
        })
      }).catch(fail)
    return () => { live = false; clearTimeout(slowTimer) }
  }, [url, attempt])

  // A radar picture loads the first time it is picked
  useEffect(() => {
    const l = model?.layers.find((x) => x.id === radar)
    if (!l || images[l.id] || missing.includes(l.id)) return
    let live = true
    twice(() => fetchImage(assetUrl(l.file), (done, total) => { if (live) setGot((g) => ({ ...g, [l.id]: [done, total] })) }))
      .then((i) => { if (live) setImages((all) => ({ ...all, [l.id]: i })) })
      .catch(() => { if (live) setMissing((m) => [...m, l.id]) })
    return () => { live = false }
  }, [radar, model, images, missing])

  // Scene, camera, lights and the render loop live as long as the panel
  useEffect(() => {
    const el = host.current!
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    } catch {
      setFailure('This browser could not start 3D graphics (WebGL).')
      return
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    el.appendChild(renderer.domElement)
    const s = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(40, 1, 0.5, 1500)
    camera.position.copy(START)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.maxPolarAngle = Math.PI * 0.48
    controls.minDistance = 4
    controls.maxDistance = 260
    controls.autoRotateSpeed = 0.5
    s.add(new THREE.HemisphereLight('#dfe9ff', '#3a2e25', 1.5))
    const sun = new THREE.DirectionalLight('#fff4e0', 2.0)
    sun.position.set(-60, 80, 40)
    s.add(sun)
    scene.current = { scene: s, camera, controls, strata: strataTexture() }
    const resize = () => {
      const { clientWidth: w, clientHeight: h } = el
      renderer.setSize(w, h)
      camera.aspect = w / Math.max(1, h)
      camera.updateProjectionMatrix()
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(el)
    // As in the lake view: while the side panel is open the picture is shifted left by half its width
    let shift = -1
    const app = el.closest('.app')
    const panelShift = () => (window.innerWidth <= 980 || app?.classList.contains('hide-right') ? 0 : 190)
    let last = performance.now()
    let frame = requestAnimationFrame(function loop(now) {
      const dt = Math.min(0.1, elapsedMs(now, last) / 1000)
      last = now
      const want = panelShift()
      const next = shift < 0 ? want : Math.abs(want - shift) < 0.5 ? want : shift + (want - shift) * Math.min(1, dt * 7)
      if (next !== shift) {
        shift = next
        const { clientWidth: w, clientHeight: h } = el
        if (shift > 0) camera.setViewOffset(w, h, shift, 0, w, h)
        else camera.clearViewOffset()
      }
      controls.update()
      renderer.render(s, camera)
      frame = requestAnimationFrame(loop)
    })
    return () => {
      cancelAnimationFrame(frame)
      ro.disconnect()
      controls.dispose()
      renderer.dispose()
      el.removeChild(renderer.domElement)
      scene.current = null
    }
  }, [])

  // The block, rebuilt when the heights arrive or the exaggeration changes
  useEffect(() => {
    const sc = scene.current
    if (!sc || !heights || !model) return
    const keepMap = (built.current?.top.material as THREE.MeshStandardMaterial | undefined)?.map ?? null
    if (built.current) { sc.scene.remove(built.current.group); built.current.group.traverse((o) => (o as THREE.Mesh).geometry?.dispose()) }
    built.current = buildBlock(model, heights, exag, sc.strata)
    ;(built.current.top.material as THREE.MeshStandardMaterial).map = keepMap
    sc.scene.add(built.current.group)
  }, [heights, exag, model])

  // The draped picture: terrain colours, then radar stability, then the reference maps on top
  useEffect(() => {
    if (!model || !images.base || !heights || !built.current) return
    const [w, h] = model.drapeSize
    const c = document.createElement('canvas')
    c.width = w
    c.height = h
    const g = c.getContext('2d')!
    g.drawImage(images.base, 0, 0, w, h)
    if (radar && images[radar]) g.drawImage(images[radar], 0, 0, w, h)
    model.layers.filter((l) => l.group !== 'radar' && on[l.id] && images[l.id]).forEach((l) => g.drawImage(images[l.id], 0, 0, w, h))
    const t = new THREE.CanvasTexture(c)
    t.colorSpace = THREE.SRGBColorSpace
    t.anisotropy = 8
    const mat = built.current.top.material as THREE.MeshStandardMaterial
    mat.map?.dispose()
    mat.map = t
    mat.needsUpdate = true
  }, [model, images, on, radar, heights, exag])

  // Place names, the UNOSAT labels and the NISAR viewing arrows
  useEffect(() => {
    const sc = scene.current
    if (!sc || !model || !heights) return
    const sx = ((model.width - 1) * model.spacingM) / 1000
    const sz = ((model.height - 1) * model.spacingM) / 1000
    const groundAt = (xM: number, yM: number) => {
      const c = Math.min(model.width - 1, Math.max(0, Math.round(xM / model.spacingM)))
      const r = Math.min(model.height - 1, Math.max(0, Math.round(yM / model.spacingM)))
      return ((heights[r * model.width + c] - model.minM) / 1000) * exag
    }
    const group = new THREE.Group()
    if (labelsOn) {
      const pin = (p: ModelLabel, colour: string, size: number, lift: number) => {
        const x = p.xM / 1000 - sx / 2
        const z = p.yM / 1000 - sz / 2
        const y = groundAt(p.xM, p.yM)
        const s = label(p.name, colour, size)
        s.position.set(x, y + lift, z)
        const stem = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x, y, z), new THREE.Vector3(x, y + lift, z)]), new THREE.LineBasicMaterial({ color: colour, depthTest: false, transparent: true }))
        stem.renderOrder = 9
        group.add(s, stem)
      }
      model.places.forEach((p) => pin(p, '#ffffff', 0.8, 1.6))
      model.markers.forEach((p, i) => pin(p, '#ffb38a', 1, 3 + i * 6))
    }
    if (tracksOn) {
      const top = ((model.maxM - model.minM) / 1000) * exag + 3
      model.tracks.forEach((t, i) => {
        // The radar looks from the satellite to the ground: the opposite of the line of sight to the sensor
        const [e, n] = t.losToSensorEastNorth
        const dir = new THREE.Vector3(-e, 0, n).normalize() // scene x is east, scene z is south
        const colour = TRACK_COLOUR[t.track] ?? '#ffffff'
        const reach = Math.abs(dir.x) > Math.abs(dir.z) ? sx / 2 : sz / 2
        const from = dir.clone().multiplyScalar(-(reach - 6)).add(new THREE.Vector3(0, top + i * 4, i === 0 ? -10 : 22))
        const arrow = new THREE.ArrowHelper(dir, from, 24, colour, 5, 3)
        group.add(arrow)
        const s = label(`Track ${t.track} looks ${compass(-e, -n)}`, colour, 1.1)
        s.position.copy(from).add(new THREE.Vector3(0, 1.5, 0))
        group.add(s)
      })
    }
    sc.scene.add(group)
    return () => { sc.scene.remove(group); disposeAll(group) }
  }, [model, heights, exag, labelsOn, tracksOn])

  useEffect(() => { if (scene.current) scene.current.controls.autoRotate = spin }, [spin])

  const reset = () => {
    const sc = scene.current
    if (!sc) return
    sc.camera.position.copy(START)
    sc.controls.target.set(0, 0, 0)
  }
  const flyTo = (p: ModelLabel) => {
    const sc = scene.current
    if (!sc || !model || !heights) return
    const sx = ((model.width - 1) * model.spacingM) / 1000
    const sz = ((model.height - 1) * model.spacingM) / 1000
    const c = Math.min(model.width - 1, Math.max(0, Math.round(p.xM / model.spacingM)))
    const r = Math.min(model.height - 1, Math.max(0, Math.round(p.yM / model.spacingM)))
    const ground = ((heights[r * model.width + c] - model.minM) / 1000) * exag
    const target = new THREE.Vector3(p.xM / 1000 - sx / 2, ground, p.yM / 1000 - sz / 2)
    sc.controls.target.copy(target)
    // From high above to the south-west, steep enough to look over the ridges in front
    sc.camera.position.copy(target).add(new THREE.Vector3(-7, 9 * exag + 12, 11))
  }

  // Progress counts only what the model needs before it can show: heights, terrain picture and the layers that start switched on
  const startIds = ['heights', 'base', ...(model?.layers.filter((l) => l.group !== 'radar' && l.on).map((l) => l.id) ?? [])]
  const loadedMb = startIds.reduce((t, id) => t + (got[id]?.[0] ?? 0), 0) / 1e6
  const totalMb = Math.max(loadedMb, startIds.reduce((t, id) => t + (got[id]?.[1] ?? 0), 0) / 1e6, model ? (model.width * model.height * 2) / 1e6 : 0)
  const refs = model?.layers.filter((l) => l.group !== 'radar') ?? []
  const radars = model?.layers.filter((l) => l.group === 'radar') ?? []
  const shownRadar = radars.find((l) => l.id === radar)
  return (
    <div className="terrain3d">
      <div className="terrain-canvas" ref={host} role="img" aria-label={`3D model of the ${model?.name ?? 'Rasuwa corridor'}, with UNOSAT maps and NASA radar layers draped over the terrain`} />
      {(!heights || !images.base) && !failure && (
        <div className="terrain-status" role="status">
          <p>Loading the 3D model{loadedMb > 0 ? `: ${loadedMb.toFixed(1)} of about ${totalMb.toFixed(1)} MB` : '…'}</p>
          {slow && <><p className="small">This is taking a while because the connection to the site seems slow. It will keep loading, or you can try again.</p><button className="ghost" onClick={() => setAttempt((a) => a + 1)}>Try again</button></>}
        </div>
      )}
      {failure && <div className="map-alert" role="alert"><p>{failure}</p><p className="small">The 3D files could not be downloaded. Check the connection and try again.</p><button className="ghost" onClick={() => setAttempt((a) => a + 1)}>Try again</button></div>}
      <section className="terrain-panel" aria-label="3D model controls">
        <p className="label">3D model</p>
        <h2>Rasuwa corridor in 3D</h2>
        <p className="muted small">Drag to turn, scroll or pinch to zoom, right-drag to move. North is towards the back. The landslide source is at the top right, and the valley runs down the Bhote Koshi and the Trishuli to the bottom left.</p>
        <p className="notice small">A picture to help read the maps. Nothing here is a forecast or a warning, and every layer below says where it comes from.</p>
        {model && <>
          <div className="row-gap">
            {model.markers.map((p) => <button key={p.name} className="ghost" onClick={() => flyTo(p)}>Go to: {p.name.replace(/ \(.*\)$/, '')}</button>)}
          </div>

          <p className="label">Maps on the terrain</p>
          <ul className="model-layers">
            {refs.map((l) => (
              <li key={l.id}>
                <label className="check"><input type="checkbox" checked={Boolean(on[l.id])} onChange={(e) => setOn((o) => ({ ...o, [l.id]: e.target.checked }))} /><i className="swatch" style={{ background: l.color }} />{l.name}</label>
                <EvidenceTag kind={l.evidence} compact />
                {missing.includes(l.id) && <p className="muted small" role="status">This picture did not load. Reopen 3D to try again.</p>}
                {l.limitations[0] && <p className="muted small">{l.limitations[0]}</p>}
              </li>
            ))}
          </ul>

          <p className="label">NASA radar layers</p>
          <div className="tabs segmented wrap" role="tablist" aria-label="Radar layer">
            <button role="tab" aria-selected={radar === ''} className={radar === '' ? 'on' : ''} onClick={() => setRadar('')}>Off</button>
            {radars.map((l) => <button key={l.id} role="tab" aria-selected={radar === l.id} className={radar === l.id ? 'on' : ''} onClick={() => setRadar(l.id)}>{l.short ?? l.id.replace('coherence-t', 'Track ')}</button>)}
          </div>
          {shownRadar && missing.includes(shownRadar.id) && <p className="muted small" role="status">This radar picture did not load. Reopen 3D to try again.</p>}
          {shownRadar && !images[shownRadar.id] && !missing.includes(shownRadar.id) && <p className="muted small" role="status">Loading the radar picture{got[shownRadar.id] ? ` (${Math.round((100 * got[shownRadar.id][0]) / Math.max(1, got[shownRadar.id][1]))}%)` : '…'}</p>}
          {shownRadar && <div className="model-layers"><p className="small">{shownRadar.name} <EvidenceTag kind={shownRadar.evidence} compact /></p>
            <p className="muted small">{shownRadar.note ?? 'Bright: the ground stayed the same between the two passes. Dark: it changed, or it is water or radar shadow. This pair spans the 26 August event, so a dark patch alone does not say what happened there.'}</p>
            {shownRadar.legend && <div className="ramp-legend small"><span>{shownRadar.legend.min} {shownRadar.legend.unit}</span><i style={{ background: `linear-gradient(to right, ${shownRadar.legend.stops.join(', ')})` }} /><span>{shownRadar.legend.max > 0 && shownRadar.legend.min < 0 ? '+' : ''}{shownRadar.legend.max} {shownRadar.legend.unit}</span></div>}
            {shownRadar.maturity && <p className="muted small">Product maturity: {shownRadar.maturity}.</p>}
            {shownRadar.limitations.map((x) => <p key={x} className="muted small">{x}</p>)}
            <p className="muted small">{shownRadar.attribution}</p></div>}

          <label className="check"><input type="checkbox" checked={tracksOn} onChange={(e) => setTracksOn(e.target.checked)} />Show which way each NISAR track looks</label>
          {tracksOn && <ul className="model-layers">
            {model.tracks.map((t) => {
              const [e, n] = t.losToSensorEastNorth
              return (
                <li key={t.track}>
                  <p className="small"><i className="swatch" style={{ background: TRACK_COLOUR[t.track] }} />Track {t.track}, {t.orbit.toLowerCase()} pass, looks {compass(-e, -n)} <EvidenceTag kind={t.evidence} compact /></p>
                  <p className="muted small">Worked out from the line-of-sight values in the NISAR files for {formatDate(t.pair[0])} to {formatDate(t.pair[1])}{t.incidenceDeg5to95 ? `, at ${t.incidenceDeg5to95[0]}° to ${t.incidenceDeg5to95[1]}° from straight down` : ''}. Slopes facing the satellite show clearly; steep slopes facing away can fall into radar shadow.</p>
                </li>
              )
            })}
          </ul>}
          <p className="muted small">The arrows are drawn far closer than the satellite's real height of 747 km.</p>

          <label className="check"><input type="checkbox" checked={labelsOn} onChange={(e) => setLabelsOn(e.target.checked)} />Show place names</label>
          {labelsOn && <p className="muted small">{model.placesLayer.name} <EvidenceTag kind={model.placesLayer.evidence} compact /> {model.placesLayer.attribution}</p>}

          <label className="slider">Height exaggeration <span>{exag.toFixed(1)}×</span>
            <input type="range" min={1} max={3} step={0.1} value={exag} onChange={(e) => setExag(Number(e.target.value))} />
          </label>
          <label className="check"><input type="checkbox" checked={spin} onChange={(e) => setSpin(e.target.checked)} />Turn slowly</label>
          <button className="ghost" onClick={reset}>Reset view</button>
          <dl className="facts">
            <div><dt>Lowest point</dt><dd>{m(model.minM)}</dd></div>
            <div><dt>Highest point</dt><dd>{m(model.maxM)}</dd></div>
            <div><dt>Area shown</dt><dd>{Math.round(((model.width - 1) * model.spacingM) / 1000)} × {Math.round(((model.height - 1) * model.spacingM) / 1000)} km</dd></div>
          </dl>
          <p className="notice small">Terrain: {model.baseLayer.name} <EvidenceTag kind={model.baseLayer.evidence} compact /> {model.baseLayer.limitations.join(' ')} Heights are sampled every {model.spacingM} m. The brown sides are decoration, not real rock layers.</p>
          <p className="muted small">{model.baseLayer.attribution}</p>
        </>}
        <footer><button className="ghost" onClick={onExit}>Close 3D</button></footer>
      </section>
    </div>
  )
}
