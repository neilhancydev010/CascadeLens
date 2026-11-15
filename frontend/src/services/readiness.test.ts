import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { blockers, modelRecords, type Readiness } from './readiness'

const r = JSON.parse(readFileSync(resolve(__dirname, '../../public/data/readiness.json'), 'utf8')) as Readiness

describe('flood and landslide readiness', () => {
  it('uses only the defined states, and claims nothing beyond the evidence on disk', () => {
    const order = ['NOT AVAILABLE', 'DATA AVAILABLE, PROCESSING REQUIRED', 'MODEL REQUIRED', 'CALIBRATION REQUIRED', 'VALIDATION REQUIRED', 'EXPERIMENTAL', 'OPERATIONALLY EVALUATED']
    const rungs: [string, string][] = [['model', 'MODEL REQUIRED'], ['calibration', 'CALIBRATION REQUIRED'], ['validation', 'VALIDATION REQUIRED'], ['operational', 'EXPERIMENTAL']]
    for (const c of r.capabilities) {
      expect(r.states, c.capability).toContain(c.state)
      if (c.state === 'CONTEXT ONLY') continue
      // A capability sits above a rung only when that rung's record exists and passed
      for (const [key, below] of rungs) {
        const check = c.checks.find((x) => x.id === `${c.capability}.${key}`)
        if (order.indexOf(c.state) > order.indexOf(below)) expect(check?.ok, `${c.capability} ${key}`).toBe(true)
      }
      // Any failing data check keeps it at or below "data available, processing required"
      if (blockers(c, 99).length > 0) expect(order.indexOf(c.state), c.capability).toBeLessThanOrEqual(1)
    }
  })

  it('lists recorded model work, including a validation that missed its criterion', () => {
    const c = { capability: 'x.L', name: 'L', family: 'landslide', state: 'VALIDATION REQUIRED', partial: [], next_requirement: null, decision: null, ceiling: null,
      checks: [{ id: 'x.L.model', ok: true, reason: 'Threshold fitted' }, { id: 'x.L.calibration', ok: true, reason: 'Level chosen' },
        { id: 'x.L.validation', ok: false, reason: 'Ran, and missed its criterion: CSI 0.04' }, { id: 'x.L.operational', ok: false, reason: 'No operational record' }] } as const
    expect(modelRecords(c as never)).toEqual(['Threshold fitted', 'Level chosen', 'Ran, and missed its criterion: CSI 0.04'])
    expect(blockers(c as never)).toEqual([])
  })

  it('says why a capability is not available, and what would unblock it', () => {
    for (const c of r.capabilities.filter((x) => x.state === 'NOT AVAILABLE')) {
      expect(blockers(c).length, c.capability).toBeGreaterThan(0)
      expect(c.next_requirement, c.capability).toBeTruthy()
    }
  })

  it('names nothing a forecast', () => {
    const text = JSON.stringify(r.capabilities.map((c) => [c.state, c.decision])).toLowerCase()
    expect(text).not.toMatch(/\bforecast (is )?(ready|available|issued)\b/)
    expect(r.capabilities.every((c) => !['EXPERIMENTAL', 'OPERATIONALLY EVALUATED'].includes(c.state))).toBe(true)
  })
})
