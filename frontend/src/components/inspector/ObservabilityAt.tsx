import { useEffect, useState } from 'react'
import type { Layer, Manifest } from '../../types/manifest'
import { samplePoint } from '../../services/sampler'
import { classify, classLabel, obsViews, reasons, STALE_NOTE, taskOf, type ObsView } from '../../services/observability'
import { isUsable } from '../../services/manifest'
import { AVAILABILITY_TEXT, nextSteps, type ViewFlags } from '../../services/nextEvidence'

const QUESTION = { disturbance: 'See a surface change?', movement: 'Measure ground movement?' }

// What to try next for one question, from the fixed rule table in nextEvidence.ts.
function NextSteps({ view, all, layers }: { view: ViewFlags; all: ViewFlags[]; layers: Layer[] }) {
  const tasks = ['disturbance', 'movement'] as const
  const items = tasks.map((t) => ({ t, steps: nextSteps(t, view, all, layers) })).filter((x) => x.steps.length)
  if (!items.length) return null
  return (
    <details className="next-steps">
      <summary>What to try next</summary>
      {items.map(({ t, steps }) => (
        <div key={t}>
          <p className="small"><strong>{QUESTION[t]}</strong></p>
          <ul className="small">
            {steps.map((s) => (
              <li key={s.rule + s.step}>
                <b>{s.step}</b> <span className={`avail a-${s.availability}`}>{AVAILABILITY_TEXT[s.availability]}</span><br />
                <span className="muted">{s.gap}. {s.detail} <span className="mono">[{s.rule}]</span></span>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <p className="muted small">Fixed rules, the same for every spot, with each rule named. A step only says data is available when it is in this build.</p>
    </details>
  )
}

// One viewing direction at the clicked point. Its own reason-flag raster is sampled, never another view's.
function ViewAt({ view, flags, titled, current, all, layers }: { view: ObsView; flags: number | null | undefined; titled: boolean; current: boolean; all: ViewFlags[] | null; layers: Layer[] }) {
  const first = view.layers[0]
  const self = all?.find((v) => v.label === view.label)
  return (
    <div className="obs-view">
      {titled && <h4>{view.label}</h4>}
      {flags === undefined ? <p className="muted small">Checking…</p> : flags === null ? (
        <p className="muted small">Not assessed at this spot: it lies outside the area checked. That is not the same as safe or unchanged.</p>
      ) : (
        <>
          {!current && <p className="notice small">{STALE_NOTE}</p>}
          <ul className="obs-tasks">
            {view.layers.map((l) => {
              const task = taskOf(l)
              const code = classify(flags, task)
              const key = l.legend?.keys?.[code - 1]
              return <li key={l.id}><span>{QUESTION[task]}</span><b style={{ color: key?.color }}><i style={{ background: key?.color }} />{classLabel(l, code)}</b></li>
            })}
          </ul>
          {reasons(flags).length > 0
            ? <ul className="obs-reasons">{reasons(flags).map((r) => <li key={r}>{r}</li>)}</ul>
            : <p className="muted small">No problems found: inside the frame, data present and not flagged by the product, not hidden by terrain, and a clear signal.</p>}
          <p className="muted small">Pair {first.acquisition.reference} to {first.acquisition.secondary}, Track {first.track}, frame {first.frames.join(', ')}. Derived by CascadeLens; method in the layer's notes.</p>
        </>
      )}
      {current && self && all && <NextSteps view={self} all={all} layers={layers} />}
    </div>
  )
}

// "Can the radar see here?" for any clicked point, whichever layer is on the map: once per viewing direction.
export function ObservabilityAt({ layers, point, current = true, manifest }: { layers: Layer[]; point: [number, number]; current?: boolean; manifest?: Manifest }) {
  const views = obsViews(layers.filter(isUsable))
  const [flags, setFlags] = useState<(number | null)[] | null>(null)
  const key = views.map((v) => v.key).join('|')
  useEffect(() => {
    let stale = false
    setFlags(null)
    Promise.all(views.map((v) => samplePoint(v.layers[0], point[0], point[1])))
      .then((rs) => { if (!stale) setFlags(rs.map((r) => (r.state === 'valid' && r.value !== undefined ? r.value : null))) })
    return () => { stale = true }
  }, [key, point]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!views.length) return null
  const all: ViewFlags[] | null = flags && views.map((v, i) => ({ label: v.label, track: v.layers[0].track ?? null, flags: flags[i] }))
  return (
    <section className="obs-at" aria-label="Can the radar see here?">
      <h3>Can the radar see here?</h3>
      {views.map((v, i) => <ViewAt key={v.key} view={v} flags={flags ? flags[i] : undefined} titled={views.length > 1} current={current} all={all} layers={manifest?.layers ?? layers} />)}
      {views.length > 1 && <p className="muted small">Each viewing direction is judged on its own. A spot one cannot judge may still be usable from the other.</p>}
    </section>
  )
}
