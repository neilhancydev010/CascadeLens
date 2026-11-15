import { useEffect, useState } from 'react'
import type { Manifest } from '../../types/manifest'
import { closureLabel, closuresOf, describe, grouped, loadAccess, type AccessDetail } from '../../services/access'

// Road access to health care, as a screen (audit P0.4). Loads its detail only when opened, so start-up stays small.
export function AccessPanel({ manifest, showStates, onShowStates }: { manifest: Manifest; showStates: boolean; onShowStates: (on: boolean) => void }) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<AccessDetail | null | undefined>(undefined)
  const [scenario, setScenario] = useState('reported')
  useEffect(() => { if (open && detail === undefined) loadAccess(manifest).then(setDetail) }, [open, detail, manifest])
  const a = manifest.access
  if (!a) return null
  const changes = detail?.healthChanges[scenario]
  const g = changes ? grouped(changes) : null
  return (
    <details className="access-panel" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>Road access to health care <span className="exp">Experimental</span></summary>
      <p className="muted small">Which named places keep a road path to a health facility when reported damage is closed. A screen to direct checks: footpaths, river crossings, helicopters and roads beyond the study area are not in this network.</p>
      <label className="check"><input type="checkbox" checked={showStates} onChange={(e) => onShowStates(e.target.checked)} />Show road and bridge states</label>
      {detail === undefined && open && <p className="muted small">Loading…</p>}
      {detail === null && <p className="muted small">The access results could not be loaded.</p>}
      {detail && g && (
        <>
          <div className="tabs segmented" role="tablist" aria-label="Access scenario">
            {detail.scenarios.filter((s) => s.id !== 'before').map((s) => (
              <button key={s.id} role="tab" aria-selected={scenario === s.id} className={scenario === s.id ? 'on' : ''} onClick={() => setScenario(s.id)}>{s.id === 'reported' ? 'Reported damage' : 'Hypothetical'}</button>
            ))}
          </div>
          <p className="small">{detail.scenarios.find((s) => s.id === scenario)?.meaning}</p>
          <p className="small"><strong>{a.summary[scenario]?.placesWithHealthPath} of {a.summary[scenario]?.places}</strong> named places keep a road path to a health facility, against {a.summary.before?.placesWithHealthPath} with every mapped road open.</p>
          {g.lost.length > 0 && <><p className="small"><strong>No road path in this network ({g.lost.length})</strong></p>
            <ul className="small access-list" title={g.lost.map(([n, c]) => `${n}: ${describe(c, 'a health facility')}`).join('\n')}>
              {g.lost.map(([name, c]) => <li key={name}><b>{name}</b>, before {c.beforeKm} km to {c.beforeTo}</li>)}
            </ul>
            <p className="small"><strong>Closed on those routes</strong></p>
            <ul className="small access-list">{closuresOf(g.lost).map(({ way, places }) => (
              <li key={way.way}><b>{closureLabel(way)}</b> ({way.state}), on {places.length} route{places.length > 1 ? 's' : ''}. <span className="muted">{way.sources.join('; ')}</span></li>
            ))}</ul></>}
          {g.longer.length > 0 && <><p className="small"><strong>Longer or different route</strong></p>
            <ul className="small access-list">{g.longer.map(([name, c]) => <li key={name}><b>{name}.</b> {describe(c, 'a health facility')}</li>)}</ul></>}
          {g.never.length > 0 && <details className="small"><summary>{g.never.length} places have no mapped road path even with every road open</summary>
            <p className="muted">{g.never.map(([n]) => n).join(', ')}. A gap in the mapping or the network, not a closure.</p></details>}
          <p className="muted small">{g.same.length} places unchanged. Destinations: {detail.healthDestinations.why}</p>
          <details className="small"><summary>How this is worked out, and its limits</summary>
            <ul>{Object.values(detail.rules).map((r) => <li key={r}>{r}</li>)}</ul>
            <p>Bridge reports matched to an OSM bridge within {detail.bridges.matchWithinM} m: {detail.bridges.reports - detail.bridges.unmatched.length} of {detail.bridges.reports}; the rest are listed in the data file and not used.</p>
            <ul>{detail.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
          </details>
        </>
      )}
    </details>
  )
}
