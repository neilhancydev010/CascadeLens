import { useMemo, useState, type FormEvent } from 'react'
import type { Manifest } from '../../types/manifest'
import type { RoadSegment } from '../../services/hazards'
import {
  addReport, CheckError, checkId, createFromRoad, merge, parseImport, setStatus, STATUS_TEXT, STATUSES, toCsv, toGeoJson, toHtml, toJson, WARNING,
  NEEDS_EVIDENCE, type CheckStatus, type FieldCheck,
} from '../../services/fieldChecks'
import { updateChecks, useChecks } from '../../services/fieldCheckStore'
import { save } from '../../services/report'

const WORKFLOW: CheckStatus[] = ['needs-verification', 'assigned', 'awaiting-field', 'unable', 'closed']

// The button under a road stretch's evidence: makes a field-check record from that real stretch, or opens the one already made.
export function AddCheckButton({ manifest, road, onOpen }: { manifest: Manifest; road: RoadSegment; onOpen?: (id: string) => void }) {
  const { checks } = useChecks()
  const [error, setError] = useState<string | null>(null)
  if (!road.id) return <p className="muted small">This stretch has no stable ID in this build, so it cannot be added to the field-check list.</p>
  const id = checkId(manifest.caseStudy.id, road.id)
  const have = checks.some((c) => c.id === id)
  const add = () => {
    try {
      if (!have) { const rec = createFromRoad(manifest, road); updateChecks((l) => [...l, rec]) }
      setError(null)
      onOpen?.(id)
    } catch (e) { setError((e as Error).message) }
  }
  return (
    <div className="add-check">
      <button onClick={add}>{have ? 'Open its field-check record' : 'Add to field-check list'}</button>
      {error && <p className="notice small" role="alert">{error}</p>}
    </div>
  )
}

function download(kind: 'pdf' | 'csv' | 'geojson' | 'json', list: FieldCheck[]) {
  const base = `cascadelens-field-checks-${new Date().toISOString().slice(0, 10)}`
  if (kind === 'csv') return save(`${base}.csv`, toCsv(list), 'text/csv')
  if (kind === 'geojson') return save(`${base}.geojson`, toGeoJson(list), 'application/geo+json')
  if (kind === 'json') return save(`${base}.json`, toJson(list), 'application/json')
  const win = window.open('', '_blank')
  if (!win) return save(`${base}.html`, toHtml(list, new Date(), true), 'text/html')
  win.document.open(); win.document.write(toHtml(list)); win.document.close()
  win.document.getElementById('print')?.addEventListener('click', () => win.print())
}

function ReportForm({ check }: { check: FieldCheck }) {
  const [observedOn, setObservedOn] = useState('')
  const [source, setSource] = useState('')
  const [finding, setFinding] = useState('')
  const [outcome, setOutcome] = useState<CheckStatus>('verified')
  const [confirmed, setConfirmed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    try {
      const next = addReport(check, { observedOn, source, finding, outcome, independentlyConfirmed: confirmed })
      updateChecks((l) => l.map((c) => (c.id === check.id ? next : c)))
      setObservedOn(''); setSource(''); setFinding(''); setConfirmed(false); setError(null)
    } catch (err) { if (err instanceof CheckError) setError(err.message); else throw err }
  }
  return (
    <form className="fc-form" onSubmit={submit} aria-label="Add a field report">
      <p className="small"><strong>Add a field report</strong></p>
      <p className="muted small">What a person or another source found on the ground. It is stored beside the satellite evidence and never changes it.</p>
      <label>What was seen<textarea value={finding} onChange={(e) => setFinding(e.target.value)} rows={3} /></label>
      <label>Observed on<input type="date" value={observedOn} onChange={(e) => setObservedOn(e.target.value)} /></label>
      <label>Who or what reported it<input value={source} onChange={(e) => setSource(e.target.value)} placeholder="Field team, agency, image ID…" /></label>
      <label>Outcome
        <select value={outcome} onChange={(e) => setOutcome(e.target.value as CheckStatus)}>
          {STATUSES.map((s) => <option key={s} value={s}>{STATUS_TEXT[s]}</option>)}
        </select>
      </label>
      <label className="check"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />Independently confirmed by someone other than the reporter</label>
      {error && <p className="notice small" role="alert">{error}</p>}
      <button type="submit" className="primary">Save field report</button>
    </form>
  )
}

function Workflow({ check }: { check: FieldCheck }) {
  const [to, setTo] = useState<CheckStatus>(check.status === 'needs-verification' ? 'assigned' : 'needs-verification')
  const [note, setNote] = useState('')
  const [assignee, setAssignee] = useState(check.assignee ?? '')
  const [error, setError] = useState<string | null>(null)
  const apply = (e: FormEvent) => {
    e.preventDefault()
    try {
      const next = setStatus(check, to, note, to === 'assigned' ? assignee : undefined)
      updateChecks((l) => l.map((c) => (c.id === check.id ? next : c)))
      setNote(''); setError(null)
    } catch (err) { if (err instanceof CheckError) setError(err.message); else throw err }
  }
  return (
    <form className="fc-form" onSubmit={apply} aria-label="Change the status">
      <p className="small"><strong>Change the status</strong></p>
      <label>New status
        <select value={to} onChange={(e) => setTo(e.target.value as CheckStatus)}>
          {WORKFLOW.map((s) => <option key={s} value={s}>{STATUS_TEXT[s]}</option>)}
        </select>
      </label>
      {to === 'assigned' && <label>Assigned to<input value={assignee} onChange={(e) => setAssignee(e.target.value)} /></label>}
      <label>Note{to === 'unable' || to === 'closed' ? ' (required)' : ''}<input value={note} onChange={(e) => setNote(e.target.value)} /></label>
      <p className="muted small">{NEEDS_EVIDENCE.map((s) => STATUS_TEXT[s]).join(' and ')} can only be set by a field report.</p>
      {error && <p className="notice small" role="alert">{error}</p>}
      <button type="submit">Update status</button>
    </form>
  )
}

function Detail({ check, onBack, onShow }: { check: FieldCheck; onBack: () => void; onShow?: (c: FieldCheck) => void }) {
  const ev = check.satellite
  return (
    <div className="fc-detail">
      <button className="link" onClick={onBack}>← All field checks</button>
      <h3 className="mono">{check.id}</h3>
      <p><span className={`fc-status s-${check.status}`}>{STATUS_TEXT[check.status]}</span>{check.assignee && <span className="muted small"> · assigned to {check.assignee}</span>}</p>
      <dl className="ev-facts">
        <dt>Stretch</dt><dd>{check.feature.road}{check.feature.bridge ? ', bridge' : ''}, {check.feature.lengthM} m{check.feature.name ? `, ${check.feature.name}` : ''}</dd>
        {check.feature.osmWay && <><dt>OSM way</dt><dd className="mono">{check.feature.osmWay}</dd></>}
        {check.feature.identityNote && <><dt>Identity</dt><dd>{check.feature.identityNote}</dd></>}
        <dt>Radar pair</dt><dd>{ev.radar.pair ?? 'None'}{ev.radar.trackFrame ? `, ${ev.radar.trackFrame}` : ''}</dd>
        {ev.radar.granule && <><dt>Source file</dt><dd className="mono wrap">{ev.radar.granule}</dd></>}
        <dt>Record made</dt><dd>{check.createdAt.slice(0, 10)}, from the evidence shown at that time</dd>
      </dl>
      {check.geometry && onShow && <button onClick={() => onShow(check)}>Show on the map</button>}
      <p className="small"><strong>Why it was flagged</strong></p><ul className="small">{check.why.map((x) => <li key={x}>{x}</li>)}</ul>
      <p className="small"><strong>What the evidence says</strong> <span className="exp">Satellite record, unchanged</span></p><ul className="small">{check.known.map((x) => <li key={x}>{x}</li>)}</ul>
      <p className="small"><strong>What remains unknown</strong></p><ul className="small">{check.unknown.map((x) => <li key={x}>{x}</li>)}</ul>
      <p className="small"><strong>What to check</strong></p><ul className="small">{check.recommended.map((x) => <li key={x}>{x}</li>)}</ul>
      <p className="small"><strong>Field reports</strong> <span className="exp">Human record</span></p>
      {check.reports.length ? (
        <ol className="fc-reports small">{check.reports.map((r) => (
          <li key={r.id}><b>{STATUS_TEXT[r.outcome]}</b>: {r.finding}<br /><span className="muted">Observed {r.observedOn} · {r.source} · {r.independentlyConfirmed ? 'independently confirmed, as stated by the user' : 'not independently confirmed'} · added {r.addedAt.slice(0, 10)} · {r.id}</span></li>
        ))}</ol>
      ) : <p className="muted small">None yet. Nothing on the ground has been reported for this stretch.</p>}
      <Workflow key={`${check.id}-${check.status}`} check={check} />
      <ReportForm check={check} />
      {check.history.length > 0 && <details className="small"><summary>Status history</summary><ul>{check.history.map((h, i) => <li key={i}>{h.at.slice(0, 16).replace('T', ' ')}: {STATUS_TEXT[h.from]} → {STATUS_TEXT[h.to]}{h.note ? ` (${h.note})` : ''}</li>)}</ul></details>}
    </div>
  )
}

// The field-check workspace: a queue of records with filters, one record's detail, exports and import.
export function FieldChecksPanel({ manifest, openId, onOpen, onShow }: { manifest: Manifest; openId: string | null; onOpen: (id: string | null) => void; onShow?: (c: FieldCheck) => void }) {
  const { checks, saved } = useChecks()
  const [status, setStatusFilter] = useState<CheckStatus | 'all'>('all')
  const [scope, setScope] = useState<'case' | 'all'>('case')
  const [note, setNote] = useState<string | null>(null)
  const shown = useMemo(() => checks.filter((c) => (scope === 'all' || c.caseId === manifest.caseStudy.id) && (status === 'all' || c.status === status)), [checks, scope, status, manifest])
  const open = checks.find((c) => c.id === openId)
  const importFile = async (f: File | undefined) => {
    if (!f) return
    try {
      const incoming = parseImport(await f.text())
      let res = { added: 0, updated: 0 }
      updateChecks((l) => { const m = merge(l, incoming); res = m; return m.list })
      setNote(`Imported: ${res.added} new record${res.added === 1 ? '' : 's'}, ${res.updated} updated with new field reports.`)
    } catch (e) { setNote((e as Error).message) }
  }
  if (open) return <section className="field-checks" aria-label="Field checks"><Detail check={open} onBack={() => onOpen(null)} onShow={onShow} /></section>
  return (
    <section className="field-checks" aria-label="Field checks">
      <h3>Field-check list</h3>
      <p className="notice small">{WARNING}</p>
      <p className="muted small">Records are saved in this browser only. They are not shared and do not sync between people or devices. Export them to pass them on.{!saved && ' This browser refused to save, so the list will be lost when the page closes: export it.'}</p>
      <div className="fc-filters">
        <label>Status
          <select value={status} onChange={(e) => setStatusFilter(e.target.value as CheckStatus | 'all')}>
            <option value="all">All</option>
            {STATUSES.map((s) => <option key={s} value={s}>{STATUS_TEXT[s]}</option>)}
          </select>
        </label>
        <label>Case
          <select value={scope} onChange={(e) => setScope(e.target.value as 'case' | 'all')}>
            <option value="case">This case</option>
            <option value="all">All cases</option>
          </select>
        </label>
      </div>
      {shown.length === 0 ? (
        <p className="muted small">{checks.length ? 'No record matches these filters.' : 'No records yet. Click a road on the map, open "Evidence for this stretch" in the Inspector, and choose "Add to field-check list".'}</p>
      ) : (
        <ul className="fc-queue">
          {shown.map((c) => (
            <li key={c.id}>
              <button onClick={() => onOpen(c.id)}>
                <span className="mono">{c.feature.id}</span> <span>{c.feature.road}{c.feature.name ? `, ${c.feature.name}` : ''}</span>
                <span className={`fc-status s-${c.status}`}>{STATUS_TEXT[c.status]}</span>
                <span className="muted small">{c.satellite.exposure} exposure · radar usable on {c.satellite.radar.shares[0]?.pct ?? '–'}% · {c.reports.length} field report{c.reports.length === 1 ? '' : 's'}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="small"><strong>Export {shown.length === checks.length ? 'all' : 'the records shown'}</strong></p>
      <div className="chips">
        {(['pdf', 'csv', 'geojson', 'json'] as const).map((k) => <button key={k} disabled={!shown.length} onClick={() => download(k, shown)}>{k === 'pdf' ? 'Field brief / PDF' : k.toUpperCase()}</button>)}
      </div>
      <label className="fc-import small">Import a JSON export<input type="file" accept="application/json,.json" onChange={(e) => { importFile(e.target.files?.[0]); e.target.value = '' }} /></label>
      {note && <p className="small" role="status">{note}</p>}
    </section>
  )
}
