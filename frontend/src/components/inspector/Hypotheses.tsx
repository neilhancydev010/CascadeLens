import { useEffect, useState } from 'react'
import type { Manifest } from '../../types/manifest'
import { explain, gather, viewSummary, type Clues, type Hypothesis, type Standing } from '../../services/hypotheses'
import { EvidenceTag } from '../explanations/EvidenceTag'

const List = ({ title, items, kind }: { title: string; items: string[]; kind: string }) =>
  items.length ? <><h5>{title}</h5><ul className={`hyp-${kind}`}>{items.map((t) => <li key={t}>{t}</li>)}</ul></> : null

const STANDING_CLASS: Record<Standing, string> = { 'Fits the checks': 'st-fits', 'Partly fits': 'st-partly', 'Little support': 'st-little', 'Cannot judge here': 'st-cannot' }

function Item({ h, open }: { h: Hypothesis; open: boolean }) {
  return (
    <details className="hyp" open={open}>
      <summary><span>{h.title}</span><b className={`standing ${STANDING_CLASS[h.standing]}`}>{h.standing}</b></summary>
      <List title="For" items={h.for} kind="for" />
      <List title="Against" items={h.against} kind="against" />
      {!h.for.length && !h.against.length && <p className="muted small">No measurement here speaks for or against it.</p>}
      <List title="Context, not counted" items={h.context} kind="context" />
      <List title="Would settle it" items={h.missing} kind="missing" />
    </details>
  )
}

function measured(c: Clues) {
  const r: [string, string][] = []
  for (const v of c.views) {
    const of = v.label ? `, ${v.label}` : ''
    if (v.coherence !== null) r.push([`Coherence${of}`, v.coherence.toFixed(2)])
    if (v.offset !== null) r.push([`Shift beyond the usual${of}`, `${v.offset.toFixed(2)} m (usual spread ${v.offsetUsual!.toFixed(2)} m)`])
  }
  if (c.elevation !== null) r.push(['Elevation', `${Math.round(c.elevation)} m`])
  if (c.slopeDeg !== null) r.push(['Slope', `${Math.round(c.slopeDeg)}°`])
  return r
}

// "What could explain this?" for the clicked spot. A screen of rules, never a probability.
export function Hypotheses({ manifest, point }: { manifest: Manifest; point: [number, number] }) {
  const [clues, setClues] = useState<Clues | null>(null)
  useEffect(() => {
    let stale = false
    setClues(null)
    gather(manifest, point).then((c) => { if (!stale) setClues(c) }).catch(() => { if (!stale) setClues(null) })
    return () => { stale = true }
  }, [manifest, point])
  return (
    <section className="hypotheses" aria-label="What could explain this?">
      <h3>What could explain this? <EvidenceTag kind="hypothesis" compact /></h3>
      {!clues ? <p className="muted small">Weighing the evidence…</p> : (
        <>
          <p className="muted small">Each explanation is checked against the radar values at this spot and independent mapping. The label counts which checks agree; it is not a probability. Context such as slope is listed but not counted.{clues.views.length > 1 ? ' Each viewing direction is read from its own data, and its checks are labelled with its track.' : ''}</p>
          {viewSummary(clues).length > 0 && <ul className="hyp-views small">{viewSummary(clues).map((t) => <li key={t}>{t}</li>)}</ul>}
          {explain(clues).map((h, i) => <Item key={h.id} h={h} open={i === 0} />)}
          {measured(clues).length > 0 && (
            <dl className="facts hyp-measured">{measured(clues).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
          )}
        </>
      )}
    </section>
  )
}
