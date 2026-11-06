import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import type { LakeSeries, LakeTerrain } from '../../types/manifest'
import { assetUrl, formatDate } from '../../services/manifest'
import { COLOUR_KEY, LakeChart } from '../compare/ComparePanel'
import { CountUp } from '../motion/CountUp'
import { buildRadarPass, buildRoute, makeGrid, type Frame } from './sims3d'

// A block model of the lake valley: Copernicus DEM heights, with a NISAR radar image draped on top and layered earth on the sides.
// Units in the scene are kilometres. North is towards the back at the start.

type Drape = 'rgb' | 'hh' | 'coh'
type Tab = 'view' | 'route' | 'radar' | 'time'
const m = (v: number) => `${Math.round(v).toLocaleString('en-GB')} m`
const TABS: [Tab, string][] = [['view', 'Look'], ['radar', 'Radar pass'], ['time', 'Time replay'], ['route', 'Steepest slope']]
const BASE_KM = 0.5 // depth of the block below the lowest point
const STRATA = ['#5b3f2c', '#6e4c34', '#4f3626', '#7a5a3f', '#433a35', '#38332f']

function strataTexture() {
  const c = document.createElement('canvas')
  c.width = 4
  c.height = 256
  const g = c.getContext('2d')!
  let y = 0
  let i = 0
  while (y < 256) {
    const h = 18 + ((i * 37) % 30)
    g.fillStyle = STRATA[i % STRATA.length]
    g.fillRect(0, y, 4, h)
    y += h
    i++
  }
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

function drapeTexture(img: HTMLImageElement, size: [number, number], outline: string | undefined, showLake: boolean) {
  const c = document.createElement('canvas')
  ;[c.width, c.height] = size
  const g = c.getContext('2d')!
  g.drawImage(img, 0, 0, size[0], size[1])
  if (outline && showLake) {
    const p = new Path2D(outline)
    g.fillStyle = 'rgba(40, 140, 255, 0.55)'
    g.fill(p, 'evenodd')
    g.strokeStyle = '#5fe0c9'
    g.lineWidth = 1.5
    g.stroke(p)
  }
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 8
  return t
}

function loadImage(url: string) {
  return new Promise<HTMLImageElement>((ok, fail) => {
    const i = new Image()
    i.onload = () => ok(i)
    i.onerror = () => fail(new Error(`Could not load ${url}`))
    i.src = url
  })
}

interface Built { top: THREE.Mesh; sides: THREE.Mesh; group: THREE.Group }

// Top surface plus four walls and a floor, all from one height grid.
function buildBlock(t: LakeTerrain, z: Float32Array, exag: number, strata: THREE.Texture): Built {
  const { width: w, height: h, spacingM } = t
  const sx = ((w - 1) * spacingM) / 1000
  const sz = ((h - 1) * spacingM) / 1000
  const y = (m: number) => ((m - t.minM) / 1000) * exag
  const top = new THREE.PlaneGeometry(sx, sz, w - 1, h - 1)
  top.rotateX(-Math.PI / 2)
  const pos = top.attributes.position as THREE.BufferAttribute
  for (let i = 0; i < pos.count; i++) pos.setY(i, y(z[i]))
  top.computeVertexNormals()

  // Walls: walk the edge, two vertices per step (ground surface and block floor)
  const edge: [number, number][] = []
  for (let c = 0; c < w; c++) edge.push([0, c])
  for (let r = 1; r < h; r++) edge.push([r, w - 1])
  for (let c = w - 2; c >= 0; c--) edge.push([h - 1, c])
  for (let r = h - 2; r >= 0; r--) edge.push([r, 0])
  const floor = -BASE_KM
  const verts: number[] = []
  const uvs: number[] = []
  const span = y(t.maxM) - floor
  let run = 0
  edge.forEach(([r, c], i) => {
    if (i > 0) {
      const [pr, pc] = edge[i - 1]
      run += Math.hypot(r - pr, c - pc) * spacingM / 1000
    }
    const x = -sx / 2 + (c * spacingM) / 1000
    const zz = -sz / 2 + (r * spacingM) / 1000
    const yy = y(z[r * w + c])
    verts.push(x, yy, zz, x, floor, zz)
    uvs.push(run, (yy - floor) / span, run, 0)
  })
  const idx: number[] = []
  for (let i = 0; i < edge.length - 1; i++) {
    const a = i * 2
    idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2)
  }
  const sides = new THREE.BufferGeometry()
  sides.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3))
  sides.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2))
  sides.setIndex(idx)
  sides.computeVertexNormals()
  strata.wrapS = THREE.RepeatWrapping
  const sideMesh = new THREE.Mesh(sides, new THREE.MeshStandardMaterial({ map: strata, roughness: 0.95, side: THREE.DoubleSide }))
  const base = new THREE.Mesh(new THREE.PlaneGeometry(sx, sz).rotateX(Math.PI / 2).translate(0, floor, 0), new THREE.MeshStandardMaterial({ color: '#2a2420' }))
  const topMesh = new THREE.Mesh(top, new THREE.MeshStandardMaterial({ roughness: 0.9, metalness: 0 }))
  const group = new THREE.Group()
  group.add(topMesh, sideMesh, base)
  return { top: topMesh, sides: sideMesh, group }
}

export function Terrain3D({ lake, onExit }: { lake: LakeSeries; onExit: () => void }) {
  const t = lake.terrain!
  const host = useRef<HTMLDivElement>(null)
  const scene = useRef<{ renderer: THREE.WebGLRenderer; scene: THREE.Scene; camera: THREE.PerspectiveCamera; controls: OrbitControls; strata: THREE.Texture } | null>(null)
  const built = useRef<Built | null>(null)
  const [heights, setHeights] = useState<Float32Array | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [di, setDi] = useState(lake.series.length - 1)
  const [drape, setDrape] = useState<Drape>('rgb')
  const [showLake, setShowLake] = useState(true)
  const [exag, setExag] = useState(1.2)
  const [spin, setSpin] = useState(false)
  const [tab, setTab] = useState<Tab>('view')
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const frames = useRef(new Set<Frame>())
  const progressRef = useRef(0)
  const sim = useRef<{ setProgress: (p: number) => void } | null>(null)
  const point = lake.series[di]

  useEffect(() => {
    let live = true
    fetch(assetUrl(t.heights)).then((r) => { if (!r.ok) throw new Error(`Heights request failed with HTTP ${r.status}`); return r.arrayBuffer() })
      .then((b) => { if (live) setHeights(new Float32Array(b)) }).catch((e: Error) => { if (live) setFailure(e.message) })
    return () => { live = false }
  }, [t.heights])

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
    const camera = new THREE.PerspectiveCamera(40, 1, 0.05, 200)
    camera.position.set(9, 10, 13)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.maxPolarAngle = Math.PI * 0.49
    controls.minDistance = 3
    controls.maxDistance = 40
    controls.autoRotateSpeed = 0.8
    s.add(new THREE.HemisphereLight('#dfe9ff', '#3a2e25', 1.4))
    const sun = new THREE.DirectionalLight('#fff4e0', 2.2)
    sun.position.set(-8, 10, 6)
    s.add(sun)
    const strata = strataTexture()
    scene.current = { renderer, scene: s, camera, controls, strata }
    const resize = () => {
      const { clientWidth: w, clientHeight: h } = el
      renderer.setSize(w, h)
      camera.aspect = w / Math.max(1, h)
      if (camera.view) camera.setViewOffset(w, h, camera.view.offsetX, 0, w, h)
      camera.updateProjectionMatrix()
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(el)
    // The canvas always fills the screen, so it never resizes while the side panel slides.
    // While the panel is open the picture is shifted left by half its width, gliding with the slide.
    let shift = -1
    const app = el.closest('.app')
    const panelShift = () => (window.innerWidth <= 980 || app?.classList.contains('hide-right') ? 0 : 190)
    let last = performance.now()
    let frame = requestAnimationFrame(function loop(now) {
      const dt = Math.min(0.1, (now - last) / 1000)
      last = now
      const want = panelShift()
      const next = shift < 0 ? want : Math.abs(want - shift) < 0.5 ? want : shift + (want - shift) * Math.min(1, dt * 7)
      if (next !== shift) {
        shift = next
        const { clientWidth: w, clientHeight: h } = el
        if (shift > 0) camera.setViewOffset(w, h, shift, 0, w, h)
        else camera.clearViewOffset()
      }
      frames.current.forEach((f) => f(dt, now))
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

  // Rebuild the block when the heights arrive or the exaggeration changes
  useEffect(() => {
    const sc = scene.current
    if (!sc || !heights) return
    if (built.current) sc.scene.remove(built.current.group)
    const keepMap = (built.current?.top.material as THREE.MeshStandardMaterial | undefined)?.map ?? null
    built.current = buildBlock(t, heights, exag, sc.strata)
    ;(built.current.top.material as THREE.MeshStandardMaterial).map = keepMap
    sc.scene.add(built.current.group)
  }, [heights, exag, t])

  // Drape the chosen date and radar view
  useEffect(() => {
    if (!point.drape || !heights) return
    let live = true
    const url = drape === 'coh' ? t.drapeCoherence : point.drape[drape]
    if (!url) return
    loadImage(assetUrl(url)).then((img) => {
      if (!live || !built.current) return
      const m = built.current.top.material as THREE.MeshStandardMaterial
      m.map?.dispose()
      m.map = tab === 'radar' ? null : drapeTexture(img, t.drapeSize, point.outlineFull, showLake)
      m.color.set(tab === 'radar' ? '#8a8580' : '#ffffff')
      m.needsUpdate = true
    }).catch((e: Error) => { if (live) setFailure(e.message) })
    return () => { live = false }
  }, [point, drape, showLake, heights, exag, t.drapeSize, tab])

  useEffect(() => { if (scene.current) scene.current.controls.autoRotate = spin }, [spin])

  const reset = () => {
    const sc = scene.current
    if (!sc) return
    sc.camera.position.set(9, 10, 13)
    sc.controls.target.set(0, 0, 0)
  }

  // Build the chosen view on the model; rebuilt when the heights, the exaggeration or the date change
  useEffect(() => {
    const sc = scene.current
    if (!sc || !heights || (tab !== 'route' && tab !== 'radar')) return
    const g = makeGrid(t, heights, exag)
    let live = true
    let made: { group: THREE.Group; setProgress: (p: number) => void; frame?: Frame; dispose: () => void } | null = null
    const attach = (m: typeof made) => {
      if (!live || !m) return
      made = m
      sc.scene.add(m.group)
      if (m.frame) frames.current.add(m.frame)
      sim.current = m
      m.setProgress(progressRef.current)
    }
    if (tab === 'route') attach(buildRoute(g))
    else if (point.drape) loadImage(assetUrl(point.drape.hh)).then((img) => attach(buildRadarPass(g, img, t.drapeSize))).catch((e: Error) => { if (live) setFailure(e.message) })
    return () => {
      live = false
      const m = made as typeof made
      if (m) { if (m.frame) frames.current.delete(m.frame); m.dispose() }
      sim.current = null
    }
  }, [tab, heights, exag, t, point])

  useEffect(() => { setPlaying(false); setProgress(0) }, [tab])
  useEffect(() => { if (tab === 'time') setShowLake(true) }, [tab])

  // Play: route and radar run 0 to 1, time replay steps through the dates
  useEffect(() => {
    if (!playing) return
    if (tab === 'time') {
      const timer = setInterval(() => setDi((i) => (i + 1) % lake.series.length), 1600)
      return () => clearInterval(timer)
    }
    let before = performance.now()
    let frame = requestAnimationFrame(function tick(now) {
      const dt = (now - before) / 1000
      before = now
      setProgress((p) => { const n = Math.min(1, p + dt / (tab === 'route' ? 8 : 10)); if (n >= 1) setPlaying(false); return n })
      frame = requestAnimationFrame(tick)
    })
    return () => cancelAnimationFrame(frame)
  }, [playing, tab, lake.series.length])

  useEffect(() => { progressRef.current = progress; sim.current?.setProgress(progress) }, [progress])

  const relief = useMemo(() => Math.round(t.maxM - t.minM), [t])
  const path = t.flowPath ?? []
  const lengthKm = path.reduce((km, q, i) => (i ? km + Math.hypot(q[0] - path[i - 1][0], q[1] - path[i - 1][1]) * t.spacingM / 1000 : 0), 0)
  const at = path.length ? Math.min(path.length - 1, Math.round(progress * (path.length - 1))) : 0
  const play = (label: string) => (
    <button className="primary" onClick={() => { if (!playing && progress >= 1) setProgress(0); setPlaying(!playing) }}>{playing ? 'Pause' : label}</button>
  )
  return (
    <div className="terrain3d">
      <div className="terrain-canvas" ref={host} role="img" aria-label={`3D model of the ${lake.name} valley on ${formatDate(point.date)}, with radar draped over the terrain`} />
      {!heights && !failure && <p className="terrain-status">Building the 3D model…</p>}
      {failure && <p className="map-alert" role="alert">{failure}</p>}
      <section className="terrain-panel" aria-label="3D model controls">
        <p className="label">3D model</p>
        <h2>{lake.name} valley in 3D</h2>
        <p className="muted small">Drag to turn, scroll or pinch to zoom, right-drag to move. North is towards the back left to start with.</p>
        <div className="tabs segmented sim3d-tabs" role="tablist" aria-label="What to show">
          {TABS.map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'on' : ''} onClick={() => setTab(id)}>{label}</button>)}
        </div>
        <div className="tab-body" key={tab}>
        {tab === 'route' && (path.length > 1 ? <>
          <p className="notice"><strong>Not a flood model.</strong> This line only follows the steepest way down from the lake's lowest shore. A real outburst flood spreads wider, carries rock and depends on how much water escapes, none of which is modelled here.</p>
          <p>Use it to read the terrain: how far and how steeply the valley drops below the dam.</p>
          <div className="sim-controls">{play(progress >= 1 ? 'Draw again' : 'Draw the line')}
            <label className="slider grow">Distance from the lake <span>{(progress * lengthKm).toFixed(1)} of {lengthKm.toFixed(1)} km</span>
              <input type="range" min={0} max={1} step={0.005} value={progress} onChange={(e) => { setPlaying(false); setProgress(Number(e.target.value)) }} />
            </label>
          </div>
          <dl className="facts">
            <div><dt>Ground height here</dt><dd>{Math.round(path[at][2]).toLocaleString('en-GB')} m</dd></div>
            <div><dt>Drop since the lake</dt><dd>{Math.round(path[0][2] - path[at][2]).toLocaleString('en-GB')} m</dd></div>
          </dl>
          <p className="notice small">Heights from the Copernicus 30 m terrain model. Below this block the valley continues as the Rolwaling Khola towards the Tamakoshi.</p>
        </> : <p className="notice">No downhill route was found for this lake.</p>)}
        {tab === 'radar' && <>
          <p>NISAR flies north to south over Nepal and looks to its left (west to east here). Watch it build its real radar picture of {formatDate(point.date)}, strip by strip.</p>
          <div className="sim-controls">{play(progress >= 1 ? 'Fly again' : 'Fly the satellite')}
            <label className="slider grow">Pass <span>{Math.round(progress * 100)}%</span>
              <input type="range" min={0} max={1} step={0.005} value={progress} onChange={(e) => { setPlaying(false); setProgress(Number(e.target.value)) }} />
            </label>
          </div>
          <p className="muted small">Dark: calm water or radar shadow. Bright: rough ground or slopes facing the radar.</p>
          <p className="notice small">The picture is the real NISAR image. The satellite is drawn far closer than its real height of 747 km.</p>
        </>}
        {tab === 'time' && <>
          <p>The four NISAR dates play on the model one after another. Watch the lake: its outline barely moves.</p>
          <div className="sim-controls">{play('Play the dates')}<span className="time-chip">{formatDate(point.date)} · {point.areaKm2.toFixed(2)} km²</span></div>
          <LakeChart lake={lake} highlight={[point.date]} />
        </>}
        {tab === 'view' && <>
        <label className="select">Radar date
          <select value={di} onChange={(e) => setDi(Number(e.target.value))}>
            {lake.series.map((p, i) => <option key={p.date} value={i}>{formatDate(p.date)}</option>)}
          </select>
        </label>
        <div className="tabs segmented" role="tablist" aria-label="Draped image">
          <button role="tab" aria-selected={drape === 'rgb'} className={drape === 'rgb' ? 'on' : ''} onClick={() => setDrape('rgb')}>Colour radar</button>
          <button role="tab" aria-selected={drape === 'hh'} className={drape === 'hh' ? 'on' : ''} onClick={() => setDrape('hh')}>Brightness</button>
          {t.drapeCoherence && <button role="tab" aria-selected={drape === 'coh'} className={drape === 'coh' ? 'on' : ''} onClick={() => setDrape('coh')}>Stability</button>}
        </div>
        <label className="slider">Height exaggeration <span>{exag.toFixed(1)}×</span>
          <input type="range" min={1} max={3} step={0.1} value={exag} onChange={(e) => setExag(Number(e.target.value))} />
        </label>
        <label className="check"><input type="checkbox" checked={showLake} onChange={(e) => setShowLake(e.target.checked)} />Show the lake in blue ({point.areaKm2.toFixed(2)} km² on this date)</label>
        </>}
        </div>
        <label className="check"><input type="checkbox" checked={spin} onChange={(e) => setSpin(e.target.checked)} />Turn slowly</label>
        <button className="ghost" onClick={reset}>Reset view</button>
        {tab === 'view' && <>
        {drape === 'rgb'
          ? <ul className="colour-key">{COLOUR_KEY.map((k) => <li key={k.label}><i style={{ background: k.color }} />{k.label}</li>)}</ul>
          : drape === 'coh'
            ? <p className="muted small">Ground stability between {lake.motion?.pair ? `${formatDate(lake.motion.pair[0])} and ${formatDate(lake.motion.pair[1])}` : 'two passes'}. Bright: the ground stayed the same. Dark: it changed, or it is water or radar shadow. The same for every date.</p>
            : <p className="muted small">Dark: calm water or radar shadow. Bright: rough ground or slopes facing the radar.</p>}
        <dl className="facts">
          <div><dt>Lowest point</dt><dd><CountUp value={t.minM} format={m} /></dd></div>
          <div><dt>Highest point</dt><dd><CountUp value={t.maxM} format={m} /></dd></div>
          {t.lakeLevelM && <div><dt>Lake surface</dt><dd>about <CountUp value={t.lakeLevelM} format={m} /></dd></div>}
          <div><dt>Relief</dt><dd><CountUp value={relief} format={m} /></dd></div>
        </dl>
        <p className="notice small">{t.note} The brown sides are decoration, not real rock layers.</p>
        </>}
        <p className="muted small">{t.attribution}</p>
        <footer><button className="ghost" onClick={onExit}>Close 3D</button></footer>
      </section>
    </div>
  )
}
