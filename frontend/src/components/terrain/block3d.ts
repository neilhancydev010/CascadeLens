import * as THREE from 'three'
import type { LakeTerrain } from '../../types/manifest'

// The terrain block shared by the 3D views: a height grid as the top surface, layered walls and a floor.
// Units are kilometres; the grid's first row is the north edge.
export type BlockGrid = Pick<LakeTerrain, 'width' | 'height' | 'spacingM' | 'minM' | 'maxM'>

export const BASE_KM = 0.5 // depth of the block below the lowest point
const STRATA = ['#5b3f2c', '#6e4c34', '#4f3626', '#7a5a3f', '#433a35', '#38332f']

export function strataTexture() {
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

export interface Built { top: THREE.Mesh; sides: THREE.Mesh; group: THREE.Group }

// Top surface plus four walls and a floor, all from one height grid.
export function buildBlock(t: BlockGrid, z: Float32Array, exag: number, strata: THREE.Texture): Built {
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

