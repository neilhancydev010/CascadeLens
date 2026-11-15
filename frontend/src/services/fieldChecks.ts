import type { Manifest } from '../types/manifest'
import type { RoadSegment } from './hazards'
import { roadEvidence, type RoadEvidence } from './roadEvidence'

// Field-check records (brief §8). A record starts from one real road stretch in the shipped screen and keeps a frozen copy of
// the satellite evidence as it was when the record was made. People then add what they found on the ground as separate,
// dated reports. A report never edits the satellite copy, and a record only becomes "Verified" or "Not confirmed" through a
// report that says what was seen, when, and by whom or from what source.
//
// Records live in this browser only (localStorage). They are not shared with anyone and do not sync between people or devices.
// Export and import as JSON is how a list moves.

export const SCHEMA = 'cascadelens.field-checks/1'
export const STORAGE_KEY = 'cascadelens.fieldChecks.v1'

export const STATUSES = ['needs-verification', 'assigned', 'awaiting-field', 'verified', 'not-confirmed', 'unable', 'closed'] as const
export type CheckStatus = (typeof STATUSES)[number]

export const STATUS_TEXT: Record<CheckStatus, string> = {
  'needs-verification': 'Needs verification',
  assigned: 'Assigned',
  'awaiting-field': 'Awaiting field information',
  verified: 'Verified',
  'not-confirmed': 'Not confirmed',
  unable: 'Unable to verify',
  closed: 'Closed with documented reason',
}

// Outcomes that claim something about the ground. They need a human report with a finding, a date and a source.
export const NEEDS_EVIDENCE: CheckStatus[] = ['verified', 'not-confirmed']
// Outcomes that end the check without a ground finding. They need a written reason.
export const NEEDS_REASON: CheckStatus[] = ['unable', 'closed']

export const WARNING = 'Satellite exposure screening is not damage, closure or safety information. A record marked "Needs verification" says only that the evidence below is worth checking on the ground. Nothing in it shows that a road is damaged, blocked, closed, safe or passable.'

export interface HumanReport {
  id: string
  addedAt: string // when it was typed into CascadeLens
  observedOn: string // when the person or source observed the ground (YYYY-MM-DD), as supplied
  source: string // who or what supplied it, as supplied: a name, an agency, a field team, an image ID
  finding: string // what they saw, in their words
  outcome: CheckStatus
  independentlyConfirmed: boolean // supplied by the user; CascadeLens cannot check it
}

export interface StatusChange { at: string; from: CheckStatus; to: CheckStatus; note: string }

export interface FieldCheck {
  schema: typeof SCHEMA
  id: string
  createdAt: string
  caseId: string
  caseName: string
  feature: { type: 'road-stretch'; id: string; osmWay: string | null; name: string | null; road: string; bridge: boolean; lengthM: number; identityNote: string | null }
  geometry: [number, number][] | null
  // frozen at creation; never edited afterwards
  satellite: RoadEvidence
  triggeringEvidence: string[]
  why: string[]
  known: string[]
  unknown: string[]
  recommended: string[]
  status: CheckStatus
  assignee: string | null
  history: StatusChange[]
  reports: HumanReport[]
}

export const checkId = (caseId: string, stretchId: string) => `FV-${caseId}-${stretchId}`

// What the shipped evidence does say about the stretch, and what it cannot.
function knownAndUnknown(ev: RoadEvidence): { known: string[]; unknown: string[] } {
  const usable = ev.radar.shares[0]?.pct
  const known = [
    `Screened as ${ev.exposure} exposure${ev.reasons.length ? ` (${ev.reasons.join('; ')})` : ', no exposure factor found'}. This is an experimental screen of terrain and position, not a damage finding.`,
    ...(usable !== null && usable !== undefined && ev.radar.pair ? [`The event radar pair (${ev.radar.pair}) could be used to spot change on ${usable}% of this stretch.`] : []),
    ...(ev.radar.otherView ? [`From at least one of two viewing directions, ${ev.radar.otherView.eitherPct}% could be used.`] : []),
    ...ev.context,
  ]
  const unknown = [
    'Whether the road is damaged, blocked, closed, safe or passable. The satellite evidence here cannot establish any of these.',
    ...(usable !== null && usable !== undefined && usable < 100 ? [`What happened on the ${Math.round(100 - usable)}% of the stretch the event pair could not use.`] : []),
    ...(!ev.radar.current ? ['The radar figures: they come from a withdrawn method.'] : []),
    'Whether anything changed after the last radar acquisition used here.',
  ]
  return { known, unknown }
}

export function createFromRoad(m: Manifest, s: RoadSegment, now = new Date()): FieldCheck {
  if (!s.id) throw new Error('This road stretch has no stable ID in this build, so a traceable record cannot be made for it.')
  const ev = roadEvidence(m, s)
  const { known, unknown } = knownAndUnknown(ev)
  return {
    schema: SCHEMA,
    id: checkId(m.caseStudy.id, s.id),
    createdAt: now.toISOString(),
    caseId: m.caseStudy.id,
    caseName: m.caseStudy.name,
    feature: {
      type: 'road-stretch', id: s.id, osmWay: ev.osmWay, name: ev.name, road: ev.road, bridge: ev.bridge, lengthM: ev.lengthM,
      identityNote: ev.osmWay ? null : 'No OpenStreetMap way ID is stored for this stretch. Identify it on the ground by its coordinates.',
    },
    geometry: s.coordinates?.length ? s.coordinates.map(([x, y]) => [+x.toFixed(6), +y.toFixed(6)] as [number, number]) : null,
    satellite: structuredClone(ev),
    triggeringEvidence: [`road-exposure:${s.id}`, ...(ev.radar.granule ? [ev.radar.granule] : []), ...(ev.radar.baselineGranule ? [ev.radar.baselineGranule] : [])],
    why: ev.reasons.length ? [...ev.reasons, ...ev.context.filter((c) => /UNOSAT|river|destroyed|High or Very high/i.test(c) && !/More than|Not on|^0% /.test(c))] : ['Added by hand. The screen found no exposure factor on this stretch.'],
    known,
    unknown,
    recommended: ev.verify,
    status: 'needs-verification',
    assignee: null,
    history: [],
    reports: [],
  }
}

export class CheckError extends Error {}

const today = (now: Date) => now.toISOString().slice(0, 10)
const isDate = (s: string) => /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(`${s}T00:00:00Z`))

// Workflow statuses only. A ground outcome goes through addReport, which checks the evidence behind it.
export function setStatus(c: FieldCheck, to: CheckStatus, note = '', assignee?: string | null, now = new Date()): FieldCheck {
  if (NEEDS_EVIDENCE.includes(to)) throw new CheckError(`"${STATUS_TEXT[to]}" needs a field report: add what was seen, when and from what source.`)
  if (NEEDS_REASON.includes(to) && !note.trim()) throw new CheckError(`"${STATUS_TEXT[to]}" needs a written reason.`)
  if (to === c.status && assignee === undefined) return c
  return {
    ...c,
    status: to,
    assignee: assignee === undefined ? c.assignee : assignee?.trim() || null,
    history: [...c.history, { at: now.toISOString(), from: c.status, to, note: note.trim() }],
  }
}

export interface ReportInput { observedOn: string; source: string; finding: string; outcome: CheckStatus; independentlyConfirmed: boolean }

export function addReport(c: FieldCheck, r: ReportInput, now = new Date()): FieldCheck {
  const finding = r.finding.trim(), source = r.source.trim()
  if (!finding) throw new CheckError('Write what was seen on the ground.')
  if (!source) throw new CheckError('Say who or what supplied this information.')
  if (!isDate(r.observedOn)) throw new CheckError('Give the date of the observation as YYYY-MM-DD.')
  if (r.observedOn > today(now)) throw new CheckError('The observation date is in the future.')
  const report: HumanReport = {
    id: `${c.id}-R${c.reports.length + 1}`,
    addedAt: now.toISOString(), observedOn: r.observedOn, source, finding, outcome: r.outcome, independentlyConfirmed: r.independentlyConfirmed,
  }
  const next = { ...c, reports: [...c.reports, report] }
  return r.outcome === c.status ? next : { ...next, status: r.outcome, history: [...c.history, { at: report.addedAt, from: c.status, to: r.outcome, note: `Field report ${report.id}` }] }
}

// ---------- storage ----------

function isRecord(x: unknown): x is FieldCheck {
  const c = x as FieldCheck
  return Boolean(c && c.schema === SCHEMA && typeof c.id === 'string' && STATUSES.includes(c.status) && c.feature?.type === 'road-stretch'
    && c.satellite && Array.isArray(c.reports) && Array.isArray(c.history))
}

export function load(store: Pick<Storage, 'getItem'> | null = safeStorage()): FieldCheck[] {
  try {
    const raw = store?.getItem(STORAGE_KEY)
    const v = raw ? JSON.parse(raw) : []
    return Array.isArray(v) ? v.filter(isRecord) : []
  } catch { return [] }
}

export function persist(list: FieldCheck[], store: Pick<Storage, 'setItem'> | null = safeStorage()): boolean {
  try { store?.setItem(STORAGE_KEY, JSON.stringify(list)); return Boolean(store) } catch { return false }
}

function safeStorage(): Storage | null {
  try { return typeof window !== 'undefined' ? window.localStorage : null } catch { return null }
}

// Merge an exported list into this one. A record new here is added as it is. For a record already here, the satellite copy
// made first is kept, and field reports from the file that are not here yet are appended.
export function merge(current: FieldCheck[], incoming: FieldCheck[]): { list: FieldCheck[]; added: number; updated: number } {
  const byId = new Map(current.map((c) => [c.id, c]))
  let added = 0, updated = 0
  for (const inc of incoming) {
    const have = byId.get(inc.id)
    if (!have) { byId.set(inc.id, inc); added++; continue }
    const seen = new Set(have.reports.map((r) => `${r.addedAt}|${r.source}|${r.finding}`))
    const extra = inc.reports.filter((r) => !seen.has(`${r.addedAt}|${r.source}|${r.finding}`))
    if (!extra.length) continue
    const reports = [...have.reports, ...extra.map((r, i) => ({ ...r, id: `${have.id}-R${have.reports.length + i + 1}` }))]
    const last = extra[extra.length - 1]
    byId.set(have.id, { ...have, reports, status: last.outcome, history: [...have.history, { at: last.addedAt, from: have.status, to: last.outcome, note: 'Imported field report' }] })
    updated++
  }
  return { list: [...byId.values()], added, updated }
}

export function parseImport(text: string): FieldCheck[] {
  let v: unknown
  try { v = JSON.parse(text) } catch { throw new CheckError('This file is not JSON.') }
  const records = (v as { schema?: string; records?: unknown[] })?.schema === SCHEMA ? (v as { records: unknown[] }).records : null
  if (!Array.isArray(records)) throw new CheckError('This is not a CascadeLens field-check export.')
  const ok = records.filter(isRecord)
  if (ok.length !== records.length) throw new CheckError(`${records.length - ok.length} of ${records.length} records in the file are incomplete, so nothing was imported.`)
  return ok
}

// ---------- exports ----------

const cell = (v: unknown) => { const s = v === null || v === undefined ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s }
const latest = (c: FieldCheck) => c.reports[c.reports.length - 1]
const centre = (c: FieldCheck): [number, number] | null => (c.geometry?.length ? c.geometry[Math.floor(c.geometry.length / 2)] : null)

export function toJson(list: FieldCheck[], now = new Date()): string {
  return JSON.stringify({ schema: SCHEMA, generatedAt: now.toISOString(), storage: 'Exported from one browser. Not synchronised with anyone.', warning: WARNING, records: list }, null, 1)
}

export function toCsv(list: FieldCheck[]): string {
  const head = ['check_id', 'case', 'stretch_id', 'osm_way', 'road', 'name', 'lng', 'lat', 'status', 'assignee', 'exposure', 'radar_usable_pct', 'radar_pair', 'source_granule',
    'why_flagged', 'what_to_verify', 'field_reports', 'last_report_date', 'last_report_source', 'last_report_independently_confirmed', 'warning']
  const rows = list.map((c) => {
    const r = latest(c), p = centre(c)
    return [c.id, c.caseId, c.feature.id, c.feature.osmWay, c.feature.road, c.feature.name, p?.[0], p?.[1], STATUS_TEXT[c.status], c.assignee, c.satellite.exposure,
      c.satellite.radar.shares[0]?.pct, c.satellite.radar.pair, c.satellite.radar.granule, c.why.join(' | '), c.recommended.join(' | '), c.reports.length,
      r?.observedOn, r?.source, r ? (r.independentlyConfirmed ? 'yes, as stated by the user' : 'no') : '', 'Exposure is not damage or closure']
  })
  return [head, ...rows].map((row) => row.map(cell).join(',')).join('\r\n') + '\r\n'
}

export function toGeoJson(list: FieldCheck[], now = new Date()): string {
  return JSON.stringify({
    type: 'FeatureCollection',
    properties: { schema: SCHEMA, generatedAt: now.toISOString(), warning: WARNING },
    features: list.map((c) => ({
      type: 'Feature',
      geometry: c.geometry ? { type: 'LineString', coordinates: c.geometry } : null,
      properties: {
        checkId: c.id, case: c.caseId, stretchId: c.feature.id, osmWay: c.feature.osmWay, road: c.feature.road, status: STATUS_TEXT[c.status],
        exposure: c.satellite.exposure, radarUsablePct: c.satellite.radar.shares[0]?.pct ?? null, radarPair: c.satellite.radar.pair, sourceGranule: c.satellite.radar.granule,
        fieldReports: c.reports.length, createdAt: c.createdAt,
      },
    })),
  }, null, 1)
}

const esc = (s: unknown) => String(s ?? '').replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]!))

// A printable field brief, one section per record. No script in the page: the app wires the print button (see ReportButtons).
export function toHtml(list: FieldCheck[], now = new Date(), selfPrinting = false): string {
  const li = (xs: string[]) => xs.map((x) => `<li>${esc(x)}</li>`).join('')
  const section = (c: FieldCheck) => {
    const p = centre(c)
    return `<section><h2>${esc(c.id)} <span class="tag">${esc(STATUS_TEXT[c.status])}</span></h2>
<table><tr><th>Stretch</th><td>${esc(c.feature.id)}: ${esc(c.feature.road)}${c.feature.bridge ? ', bridge' : ''}, ${c.feature.lengthM} m${c.feature.name ? `, ${esc(c.feature.name)}` : ''}</td></tr>
${c.feature.osmWay ? `<tr><th>OpenStreetMap</th><td>${esc(c.feature.osmWay)}</td></tr>` : ''}
${p ? `<tr><th>Middle of stretch</th><td>${p[1].toFixed(5)}° N, ${p[0].toFixed(5)}° E</td></tr>` : ''}
${c.feature.identityNote ? `<tr><th>Identity</th><td>${esc(c.feature.identityNote)}</td></tr>` : ''}
<tr><th>Radar pair</th><td>${esc(c.satellite.radar.pair ?? 'none')}${c.satellite.radar.trackFrame ? `, ${esc(c.satellite.radar.trackFrame)}` : ''}</td></tr>
<tr><th>Source file</th><td style="word-break:break-all">${esc(c.satellite.radar.granule ?? 'none')}</td></tr>
<tr><th>Record made</th><td>${esc(c.createdAt.slice(0, 10))}${c.assignee ? `, assigned to ${esc(c.assignee)}` : ''}</td></tr></table>
<h3>Why it was flagged</h3><ul>${li(c.why)}</ul>
<h3>What the evidence says</h3><ul>${li(c.known)}</ul>
<h3>What remains unknown</h3><ul>${li(c.unknown)}</ul>
<h3>What to check</h3><ul>${li(c.recommended)}</ul>
<h3>Field reports</h3>${c.reports.length ? `<table><tr><th>Observed</th><th>Source</th><th>Finding</th><th>Outcome</th><th>Independently confirmed</th></tr>
${c.reports.map((r) => `<tr><td>${esc(r.observedOn)}</td><td>${esc(r.source)}</td><td>${esc(r.finding)}</td><td>${esc(STATUS_TEXT[r.outcome])}</td><td>${r.independentlyConfirmed ? 'Yes, as stated by the user' : 'No'}</td></tr>`).join('')}</table>` : '<p class="muted">None yet. Nothing on the ground has been reported for this stretch.</p>'}
</section>`
  }
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>CascadeLens field-check brief</title><style>
body{font:13px/1.45 system-ui,sans-serif;color:#111;max-width:820px;margin:24px auto;padding:0 16px}h1{font-size:20px}h2{font-size:15px;margin-top:26px;border-bottom:1px solid #ccc}h3{font-size:13px;margin:12px 0 4px}
table{border-collapse:collapse;width:100%;font-size:12px}td,th{border:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:top}.muted{color:#555}.tag{font-size:11px;border:1px solid #999;border-radius:8px;padding:0 6px;font-weight:normal}
.warn{border:2px solid #b45309;padding:8px 10px;background:#fff7ed}section{break-inside:avoid-page}@media print{button{display:none}}</style></head><body>
<button id="print"${selfPrinting ? ' onclick="print()"' : ''}>Print or save as PDF</button>
<h1>CascadeLens field-check brief</h1>
<p class="muted">${list.length} record${list.length === 1 ? '' : 's'} · generated ${esc(now.toISOString().slice(0, 16).replace('T', ' '))} UTC · stored in one browser, not shared</p>
<p class="warn"><b>Read first.</b> ${esc(WARNING)}</p>
${list.map(section).join('')}
</body></html>`
}
