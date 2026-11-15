import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { Manifest } from '../types/manifest'
import { finding } from './finding'

const root = resolve(__dirname, '../../..')
const shipped = () => JSON.parse(readFileSync(resolve(__dirname, '../../public/data/manifests/manifest.json'), 'utf8')) as Manifest

describe('first-minute finding', () => {
  it('quotes the shipped figures', () => {
    const m = shipped()
    const f = finding(m)!
    const text = f.points.map((p) => p.text).join(' ')
    const co = m.controlSeries!.pairs.find((p) => p.pair[0] === '2026-08-16')!
    expect(text).toContain(co.inside.toFixed(2))
    expect(text).toContain(co.outside.toFixed(2))
    expect(f.points).toHaveLength(3)
    expect(text).toMatch(/beyond the radar frames checked \(74 and 75\)/)
  })
  it('follows the data rather than fixed numbers', () => {
    const m = shipped()
    m.controlSeries!.pairs.forEach((p) => { p.inside = 0.111 })
    expect(finding(m)!.points[0].text).toContain('0.11')
  })
  it('reports an observation, not a cause, and says why the pairs are not like for like', () => {
    const text = finding(shipped())!.points.map((p) => p.text).join(' ')
    expect(text).not.toMatch(/specific to the mudflow|not the season/)
    expect(text).toContain('consistent with surface change')
    expect(text).toContain('does not establish the cause')
    expect(text).toMatch(/24 days and the event pair 12/)
    expect(text).toContain('different radar modes (4000 and 2000')
  })
  it('withholds observability figures from the earlier method, and shows them once recomputed', () => {
    const m = shipped()
    m.observability!.methodVersion = undefined
    expect(finding(m)!.points.map((p) => p.text).join(' ')).toContain('withheld until the corrected run')
    m.observability!.methodVersion = 2
    expect(finding(m)!.points.map((p) => p.text).join(' ')).toContain('could be judged on')
  })
  it('stays away when the case has no control comparison', () => {
    const m = shipped()
    m.controlSeries = undefined
    expect(finding(m)).toBeNull()
  })
})

describe('status registry', () => {
  const s = JSON.parse(readFileSync(resolve(__dirname, '../../public/data/status.json'), 'utf8'))
  it('uses only the defined maturity levels', () => {
    for (const c of s.capabilities) expect(s.levels).toContain(c.maturity)
  })
  it('backs every "complete and tested" claim with a test that exists', () => {
    for (const c of s.capabilities.filter((x: { maturity: string }) => x.maturity === 'COMPLETE AND TESTED')) {
      expect(c.tests.length, c.id).toBeGreaterThan(0)
      for (const t of c.tests) expect(existsSync(resolve(root, t.split('::')[0])), t).toBe(true)
    }
  })
  // A test file that exists is not enough: at least one must call the computation the claim is about ("file::symbol").
  it('names, for every "complete and tested" claim, a test that calls the computation behind it', () => {
    for (const c of s.capabilities.filter((x: { maturity: string }) => x.maturity === 'COMPLETE AND TESTED')) {
      const named = c.tests.filter((t: string) => t.includes('::'))
      expect(named.length, `${c.id} names no function its test calls`).toBeGreaterThan(0)
    }
    for (const c of s.capabilities) {
      for (const t of c.tests.filter((x: string) => x.includes('::'))) {
        const [file, symbol] = t.split('::')
        expect(readFileSync(resolve(root, file), 'utf8'), `${c.id}: ${file} never uses ${symbol}`).toContain(symbol)
      }
    }
  })
})
