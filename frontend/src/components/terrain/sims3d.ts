import * as THREE from 'three'
import type { LakeTerrain } from '../../types/manifest'

// Animated 3D views on the block model, drawn only from real data (DEM heights and NISAR images). Units: kilometres. Every scene object here is removed by its dispose().

export interface Frame { (dt: number, now: number): void }

export interface Grid {
  t: LakeTerrain
  z: Float32Array
  exag: number
  sp: number
  sx: number
  sz: number
  y: (m: number) => number
  at: (c: number, r: number, m: number) => THREE.Vector3
}

export function makeGrid(t: LakeTerrain, z: Float32Array, exag: number): Grid {
  const sp = t.spacingM / 1000
  const sx = (t.width - 1) * sp
  const sz = (t.height - 1) * sp
  const y = (m: number) => ((m - t.minM) / 1000) * exag
  return { t, z, exag, sp, sx, sz, y, at: (c, r, m) => new THREE.Vector3(-sx / 2 + c * sp, y(m), -sz / 2 + r * sp) }
}

function disposeAll(group: THREE.Object3D) {
  group.traverse((o) => {
    const m = o as THREE.Mesh
    m.geometry?.dispose()
    const mat = m.material as THREE.Material | THREE.Material[] | undefined
    ;(Array.isArray(mat) ? mat : mat ? [mat] : []).forEach((x) => { (x as THREE.MeshBasicMaterial).map?.dispose(); x.dispose() })
  })
  group.removeFromParent()
}

// ---------- Downhill route: the path water would take from the lake's lowest shore (real DEM, no flood physics) ----------

export interface Route { group: THREE.Group; setProgress: (p: number) => void; dispose: () => void }

export function buildRoute(g: Grid): Route | null {
  const path = g.t.flowPath
  if (!path || path.length < 2) return null
  const pts = path.map(([c, r, m]) => g.at(c, r, m).add(new THREE.Vector3(0, 0.025, 0)))
  const curve = new THREE.CatmullRomCurve3(pts, false, 'centripetal')
  const segments = Math.max(64, pts.length * 4)
  const radial = 10
  const line = new THREE.Mesh(new THREE.TubeGeometry(curve, segments, 0.05, radial, false), new THREE.MeshStandardMaterial({ color: '#2f8cff', emissive: '#1a5dff', emissiveIntensity: 0.5, roughness: 0.3 }))
  const marker = new THREE.Mesh(new THREE.SphereGeometry(0.08, 20, 14), new THREE.MeshBasicMaterial({ color: '#ffffff' }))
  const group = new THREE.Group()
  group.add(line, marker)
  const total = segments * radial * 6
  const setProgress = (p: number) => {
    const q = Math.min(1, Math.max(0, p))
    line.geometry.setDrawRange(0, Math.floor((q * total) / (radial * 6)) * radial * 6)
    marker.position.copy(curve.getPointAt(Math.max(0.001, q)))
    marker.visible = q > 0
  }
  setProgress(0)
  return { group, setProgress, dispose: () => disposeAll(group) }
}

// ---------- Radar pass: NISAR flying north to south, painting its real image of this date as it goes ----------

export interface RadarPass { group: THREE.Group; setProgress: (p: number) => void; frame: Frame; dispose: () => void }

export function buildRadarPass(g: Grid, picture: HTMLImageElement, size: [number, number]): RadarPass {
  const { width: w, height: h } = g.t
  const group = new THREE.Group()
  const top = g.y(g.t.maxM)
  const alt = top + 1.8
  const trackX = -g.sx / 2 - 1.1

  // Satellite: bus, two solar wings, the big round radar reflector on a boom
  const sat = new THREE.Group()
  sat.add(new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.2, 0.36), new THREE.MeshStandardMaterial({ color: '#d9b45a', metalness: 0.6, roughness: 0.35 })))
  for (const s of [-1, 1]) {
    const wing = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.02, 0.9), new THREE.MeshStandardMaterial({ color: '#24407a', metalness: 0.3, roughness: 0.4, emissive: '#0b1c3a' }))
    wing.position.set(0, 0.05, s * 0.65)
    sat.add(wing)
  }
  const dish = new THREE.Mesh(new THREE.CircleGeometry(0.42, 40), new THREE.MeshStandardMaterial({ color: '#e8eef2', metalness: 0.5, roughness: 0.3, side: THREE.DoubleSide }))
  dish.position.set(0.45, -0.25, 0)
  dish.rotation.set(0, Math.PI / 2, -0.75)
  sat.add(dish)
  group.add(sat)

  // Beam: a fan from the reflector to a line across the ground at the satellite's position
  const fanN = w
  const fanGeo = new THREE.BufferGeometry()
  const fanPos = new Float32Array((fanN + 1) * 3)
  fanGeo.setAttribute('position', new THREE.BufferAttribute(fanPos, 3))
  const idx: number[] = []
  for (let i = 1; i < fanN; i++) idx.push(0, i, i + 1)
  fanGeo.setIndex(idx)
  const fan = new THREE.Mesh(fanGeo, new THREE.MeshBasicMaterial({ color: '#7ff5e0', transparent: true, opacity: 0.22, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending }))
  group.add(fan)
  const lineGeo = new THREE.BufferGeometry()
  const linePos = new Float32Array(fanN * 3)
  lineGeo.setAttribute('position', new THREE.BufferAttribute(linePos, 3))
  const line = new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ color: '#b6fff2' }))
  group.add(line)

  // The real radar picture, revealed from north to south behind the beam
  const canvas = document.createElement('canvas')
  ;[canvas.width, canvas.height] = size
  const ctx = canvas.getContext('2d')!
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 8
  const overlayGeo = new THREE.PlaneGeometry(g.sx, g.sz, w - 1, h - 1)
  overlayGeo.rotateX(-Math.PI / 2)
  const op = overlayGeo.attributes.position as THREE.BufferAttribute
  for (let i = 0; i < op.count; i++) op.setY(i, g.y(g.z[i]) + 0.006)
  overlayGeo.computeVertexNormals()
  const overlay = new THREE.Mesh(overlayGeo, new THREE.MeshStandardMaterial({ map: tex, transparent: true, roughness: 0.9, polygonOffset: true, polygonOffsetFactor: -2 }))
  overlay.renderOrder = 3
  group.add(overlay)

  const paint = (frac: number) => {
    const [cw, ch] = size
    ctx.clearRect(0, 0, cw, ch)
    const rows = Math.round(ch * frac)
    if (rows > 0) ctx.drawImage(picture, 0, 0, picture.width, (picture.height * rows) / ch, 0, 0, cw, rows)
    tex.needsUpdate = true
  }

  const setProgress = (p: number) => {
    const zz = -g.sz / 2 - 1.5 + p * (g.sz + 3)
    sat.position.set(trackX, alt, zz)
    const r = Math.round(((zz + g.sz / 2) / g.sz) * (h - 1))
    const rr = Math.min(h - 1, Math.max(0, r))
    fan.visible = line.visible = r >= 0 && r < h
    fanPos.set([trackX + 0.45, alt - 0.25, zz], 0)
    for (let c = 0; c < fanN; c++) {
      const v = g.at(c, rr, g.z[rr * w + c])
      fanPos.set([v.x, v.y + 0.01, v.z], (c + 1) * 3)
      linePos.set([v.x, v.y + 0.015, v.z], c * 3)
    }
    fanGeo.attributes.position.needsUpdate = true
    lineGeo.attributes.position.needsUpdate = true
    fanGeo.computeBoundingSphere()
    lineGeo.computeBoundingSphere()
    paint(Math.min(1, Math.max(0, (r + 1) / h)))
  }
  setProgress(0)
  const frame: Frame = (_dt, now) => { (fan.material as THREE.MeshBasicMaterial).opacity = 0.16 + 0.08 * Math.sin(now / 90) }
  return { group, setProgress, frame, dispose: () => { tex.dispose(); disposeAll(group) } }
}
