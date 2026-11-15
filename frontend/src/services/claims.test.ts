import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

// The claim register (public/data/claims.json) is the single list of headline claims and whether each may be shown.
// A RED claim must not come back: its wording is searched for on every live surface the register names.
const root = resolve(__dirname, '../../..')
const register = JSON.parse(readFileSync(resolve(__dirname, '../../public/data/claims.json'), 'utf8')) as {
  statuses: string[]
  surfaces: string[]
  claims: { id: string; claim: string; status: string; basis: string; action: string; resolution?: string; forbidden: string[] }[]
}

function files(path: string): string[] {
  const full = resolve(root, path)
  if (!statSync(full).isDirectory()) return [full]
  return readdirSync(full).flatMap((n) => {
    const p = join(full, n)
    if (statSync(p).isDirectory()) return files(join(path, n))
    return /\.(ts|tsx|json|md|txt)$/.test(n) && !/\.test\.tsx?$/.test(n) ? [p] : []
  })
}

describe('claim register', () => {
  it('uses unique IDs and only the defined statuses, and every claim states its basis and action', () => {
    const ids = register.claims.map((c) => c.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const c of register.claims) {
      expect(register.statuses, c.id).toContain(c.status)
      expect(c.basis.length, c.id).toBeGreaterThan(0)
      expect(c.action.length, c.id).toBeGreaterThan(0)
    }
  })

  it('records how every RED claim was resolved, and the wording to keep out', () => {
    for (const c of register.claims.filter((x) => x.status === 'RED')) {
      expect(c.resolution, `${c.id} is RED with no resolution`).toBeTruthy()
      expect(c.forbidden.length, `${c.id} names no wording to keep out`).toBeGreaterThan(0)
    }
  })

  it('names live surfaces that exist', () => {
    for (const s of register.surfaces) expect(existsSync(resolve(root, s)), s).toBe(true)
  })

  it('keeps the wording of every RED claim off every live surface', () => {
    const texts = register.surfaces.flatMap(files).map((f) => [f, readFileSync(f, 'utf8').toLowerCase()] as const)
    for (const c of register.claims.filter((x) => x.status === 'RED')) {
      for (const phrase of c.forbidden) {
        const hits = texts.filter(([, t]) => t.includes(phrase.toLowerCase())).map(([f]) => f.replace(`${root}/`, ''))
        expect(hits, `${c.id} "${phrase}" is back in ${hits.join(', ')}`).toEqual([])
      }
    }
  })
})
