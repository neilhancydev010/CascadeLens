import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe as suite, expect, it } from 'vitest'
import { describe, grouped, type AccessChange, type AccessDetail } from './access'

const detail = JSON.parse(readFileSync(resolve(__dirname, '../../public/data/access/rasuwa-2026.json'), 'utf8')) as AccessDetail
const manifest = JSON.parse(readFileSync(resolve(__dirname, '../../public/data/manifests/manifest.json'), 'utf8'))

suite('road access screen', () => {
  it('never calls a place isolated, cut off or safe, in any sentence it can write', () => {
    const all = Object.values(detail.healthChanges).flatMap((s) => Object.values(s)).concat(Object.values(detail.helipadChanges).flatMap((s) => Object.values(s)))
    for (const c of all) {
      const text = describe(c, 'a health facility').toLowerCase()
      for (const word of ['isolat', 'cut off', 'safe', 'unreachable']) expect(text, text).not.toContain(word)
    }
  })

  it('names the closures and their sources when a place loses its road path', () => {
    const lost = grouped(detail.healthChanges.reported).lost
    expect(lost.length).toBeGreaterThan(0)
    for (const [, c] of lost) {
      expect(c.closedOnRoute?.length, 'a lost path names what closed it').toBeGreaterThan(0)
      expect(describe(c, 'a health facility')).toContain('Closed on that route')
    }
  })

  it('tells a mapping gap apart from a closure', () => {
    const c: AccessChange = { change: 'no path in either', reason: 'No road path in this network' }
    expect(describe(c, 'a health facility')).toContain('not a closure')
  })

  it('keeps the manifest summary in step with the detail file', () => {
    for (const s of detail.scenarios) {
      const kept = Object.values(detail.healthChanges[s.id] ?? {}).filter((c) => !['no path', 'no path in either'].includes(c.change)).length
      if (s.id !== 'before') expect(manifest.access.summary[s.id].placesWithHealthPath, s.id).toBe(kept)
    }
  })

  it('defaults every way without a report to unknown, and never assumes open', () => {
    expect(detail.states.unknown.ways).toBeGreaterThan(detail.states.open.ways)
    expect(detail.rules.states).toContain('unknown: no report (the default)')
  })
})

suite('road access closures', () => {
  it('lists each closure once, with every affected place', async () => {
    const { closuresOf } = await import('./access')
    const lost = grouped(detail.healthChanges.reported).lost
    const list = closuresOf(lost)
    expect(new Set(list.map((x) => x.way.way)).size).toBe(list.length)
    const total = lost.reduce((n, [, c]) => n + (c.closedOnRoute?.length ?? 0), 0)
    expect(list.reduce((n, x) => n + x.places.length, 0)).toBe(total)
  })
})
