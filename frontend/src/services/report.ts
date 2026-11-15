import type { Manifest } from '../types/manifest'
import { acquisitionLabel, coordinates, isUsable } from './manifest'
import { samplePoint } from './sampler'
import { evidenceOf, EVIDENCE } from './evidence'
import { classify, classLabel, isObservability, obsViews, observabilityCurrent, reasons, STALE_NOTE, taskOf } from './observability'
import { explain, gather, viewSummary, type Hypothesis } from './hypotheses'
import { isTerrainScreen, nearestRoad, terrainClass, terrainFactors, terrainLayer } from './hazards'
import { roadEvidence, type RoadEvidence } from './roadEvidence'

// One evidence report for one clicked spot: every value read there, where it came from, and what it can and cannot say.

export interface ReportRow {
  layer: string
  layerId: string
  evidence: string
  state: string
  value: number | null
  units: string | null
  observation: string
  source: string | null
}

export interface ObsAnswer { pair: string; frame: string; methodVersion: number; current: boolean; answers: { question: string; answer: string }[]; reasons: string[] }

export interface Report {
  title: string
  generatedAt: string
  case: { id: string; name: string; eventDate: string }
  point: { lng: number; lat: number }
  observability: ObsAnswer | null
  // further viewing directions (another track), each judged from its own flags
  otherViews?: ObsAnswer[]
  readings: ReportRow[]
  explanations: Hypothesis[]
  // what each viewing direction could read at the spot, when there is more than one
  explanationViews?: string[]
  hazards?: { terrain: { class: string; factors: string[] } | null; road: RoadEvidence | null; maturity: string }
  notes: string[]
}

const QUESTION = { disturbance: 'Could a surface change be seen here?', movement: 'Could ground movement be measured here?' }

export async function buildReport(m: Manifest, p: [number, number], now = new Date()): Promise<Report> {
  const usable = m.layers.filter((l) => isUsable(l) && l.status !== 'renderable' && l.sources.some((s) => s.sampling))
  const obs = usable.filter(isObservability)
  const plain = usable.filter((l) => !isObservability(l) && !isTerrainScreen(l))
  const tl = terrainLayer(m)
  const views = obsViews(obs)
  const [samples, clues, flagSamples, tSample, road] = await Promise.all([
    Promise.all(plain.map((l) => samplePoint(l, p[0], p[1]))),
    gather(m, p),
    Promise.all(views.map((v) => samplePoint(v.layers[0], p[0], p[1]))),
    tl ? samplePoint(tl, p[0], p[1]) : Promise.resolve(null),
    m.hazards ? nearestRoad(m, p) : Promise.resolve(null),
  ])
  const tf = tSample?.state === 'valid' && tSample.value !== undefined ? tSample.value : null
  const o = obs[0]
  const answer = (i: number): ObsAnswer => {
    const s = flagSamples[i], ls = views[i].layers, first = ls[0]
    const flags = s.state === 'valid' && s.value !== undefined ? s.value : null
    return {
      pair: `${first.acquisition.reference} to ${first.acquisition.secondary}`,
      frame: views[i].label,
      methodVersion: m.observability?.methodVersion ?? 1,
      current: observabilityCurrent(m),
      answers: ls.map((l) => ({ question: QUESTION[taskOf(l)], answer: flags === null ? 'Not assessed here' : classLabel(l, classify(flags, taskOf(l))) })),
      reasons: flags === null ? ['Outside the area checked. That is not the same as safe or unchanged.'] : reasons(flags),
    }
  }
  return {
    title: `CascadeLens evidence report: ${m.caseStudy.name}`,
    generatedAt: now.toISOString(),
    case: { id: m.caseStudy.id, name: m.caseStudy.name, eventDate: m.caseStudy.eventDate },
    point: { lng: +p[0].toFixed(6), lat: +p[1].toFixed(6) },
    observability: views.length ? answer(0) : null,
    ...(views.length > 1 ? { otherViews: views.slice(1).map((_, i) => answer(i + 1)) } : {}),
    readings: plain.map((l, i) => ({
      layer: l.name, layerId: l.id, evidence: EVIDENCE[evidenceOf(l)].label, state: samples[i].state,
      value: samples[i].state === 'valid' && samples[i].value !== undefined ? samples[i].value! : null,
      units: l.units, observation: acquisitionLabel(l), source: samples[i].granule ?? null,
    })),
    explanations: explain(clues),
    ...(viewSummary(clues).length ? { explanationViews: viewSummary(clues) } : {}),
    hazards: m.hazards ? { terrain: tf === null ? null : { class: m.hazards.terrain.classes.find((c) => c.code === terrainClass(tf))?.label ?? '', factors: terrainFactors(tf) }, road: road ? roadEvidence(m, road) : null, maturity: 'Experimental screens, not forecasts' } : undefined,
    notes: [
      'Values are the nearest stored pixel, with no interpolation. A blank value means no valid observation, which is not the same as no change.',
      'Explanations are a rule-based screen: they count which checks agree, using radar values at this spot and independent mapping. Context such as slope is listed but not counted. They are hypotheses, not probabilities or verdicts.',
      ...(o && !observabilityCurrent(m) ? [`Radar observability: ${STALE_NOTE}`] : []),
      'NISAR products are provisional releases. This report is a retrospective research aid, not a warning.',
    ],
  }
}

const cell = (v: unknown) => { const s = v === null || v === undefined ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s }

export function toCsv(r: Report): string {
  const head = ['case', 'lng', 'lat', 'layer', 'layer_id', 'evidence', 'state', 'value', 'units', 'observation', 'source']
  const rows = r.readings.map((x) => [r.case.id, r.point.lng, r.point.lat, x.layer, x.layerId, x.evidence, x.state, x.value, x.units, x.observation, x.source])
  const road = r.hazards?.road
  // The nearest road stretch, as one row: its ID, its rating, and the share of it the event pair could use for change
  if (road) rows.push([r.case.id, r.point.lng, r.point.lat, `Road stretch ${road.id ?? ''} (${road.road}, ${road.distanceM} m away)`.replace('  ', ' '), road.id, 'Derived',
    `${road.exposure} exposure; ${road.radar.watch}${road.radar.otherView ? `; from either direction: ${road.radar.otherView.watch} (${road.radar.otherView.eitherPct}%)` : ''}`, road.radar.shares[0].pct, '% usable for change', road.radar.pair, road.radar.granule])
  return [head, ...rows].map((row) => row.map(cell).join(',')).join('\r\n') + '\r\n'
}

export function toGeoJson(r: Report): string {
  const { point, readings, ...rest } = r
  return JSON.stringify({ type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [point.lng, point.lat] },
    properties: { ...rest, readings: readings.filter((x) => x.value !== null).map((x) => ({ layerId: x.layerId, value: x.value, units: x.units })) } }] }, null, 1)
}

const esc = (s: unknown) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!))

function roadHtml(ev: RoadEvidence, li: (xs: string[]) => string): string {
  const row = (k: string, v: unknown) => (v === null || v === undefined || v === '' ? '' : `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`)
  return `<h3>Road stretch ${esc(ev.id ?? '')}</h3><table>
${row('Road', `${ev.road}${ev.bridge ? ', bridge' : ''}, ${ev.lengthM} m long, ${ev.distanceM} m from the spot`)}${row('Name', ev.name)}${row('OpenStreetMap', ev.osmWay)}
${row('Rating', `${ev.exposure} exposure${ev.reasons.length ? `: ${ev.reasons.join('; ')}` : ': no factor found'}`)}
${row('Radar pair', ev.radar.pair ? `${ev.radar.pair}${ev.radar.trackFrame ? `, ${ev.radar.trackFrame}` : ''}` : null)}${row('Before pair', ev.radar.baseline)}${row('Source file', ev.radar.granule)}
${row('Observability', `Method version ${ev.radar.methodVersion}${ev.radar.current ? '' : ' (withdrawn; awaiting the rebuild)'}. ${ev.radar.watch}.`)}
${ev.radar.shares.map((s) => row(s.label, s.pct === null ? 'not in this build' : `${s.pct}%`)).join('')}
${ev.radar.otherView ? row('Opposite direction', `${ev.radar.otherView.label}${ev.radar.otherView.pair ? `, ${ev.radar.otherView.pair}` : ''}: ${ev.radar.otherView.usablePct}% usable for change; ${ev.radar.otherView.eitherPct}% from either direction (${ev.radar.otherView.watch})`) : ''}</table>
<p><b>Context</b></p><ul>${li(ev.context)}</ul><p><b>What to verify</b></p><ul>${li(ev.verify)}</ul>`
}

// The app's offline policy forbids scripts written into a page, and a window the app opens inherits that policy.
// So the print button carries no script by default: the app wires it up from outside (see ReportButtons).
// `selfPrinting` is for the saved-file fallback, which opens from disk under no policy and has nobody to wire it.
export function toHtml(r: Report, selfPrinting = false): string {
  const li = (xs: string[]) => xs.map((x) => `<li>${esc(x)}</li>`).join('')
  const num = (v: number | null) => (v === null ? '' : Math.abs(v) >= 1000 ? v.toFixed(1) : v.toPrecision(5))
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${esc(r.title)}</title><style>
body{font:14px/1.45 system-ui,sans-serif;color:#111;max-width:820px;margin:24px auto;padding:0 16px}h1{font-size:20px}h2{font-size:15px;margin-top:22px;border-bottom:1px solid #ccc}
table{border-collapse:collapse;width:100%;font-size:12px}td,th{border:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:top}.muted{color:#555}.tag{font-size:11px;border:1px solid #999;border-radius:8px;padding:0 6px}
@media print{button{display:none}}</style></head><body>
<button id="print"${selfPrinting ? ' onclick="print()"' : ''}>Print or save as PDF</button>
<h1>${esc(r.title)}</h1>
<p class="muted">Spot ${coordinates(r.point.lng, r.point.lat)} · event ${esc(r.case.eventDate)} · generated ${esc(r.generatedAt.slice(0, 16).replace('T', ' '))} UTC</p>
${r.observability ? `<h2>Can the radar see here? <span class="tag">Derived</span></h2>
${[r.observability, ...(r.otherViews ?? [])].map((v) => `<p class="muted">Pair ${esc(v.pair)}, ${esc(v.frame)}, method version ${v.methodVersion}</p>
${v.current ? '' : `<p><b>${esc(STALE_NOTE)}</b></p>`}
<table>${v.answers.map((a) => `<tr><th>${esc(a.question)}</th><td>${esc(a.answer)}</td></tr>`).join('')}</table>
${v.reasons.length ? `<ul>${li(v.reasons)}</ul>` : '<p>No problems found at this spot.</p>'}`).join('')}${r.otherViews?.length ? '<p class="muted">Each viewing direction is judged on its own flags.</p>' : ''}` : ''}
<h2>What could explain this? <span class="tag">Hypothesis</span></h2>
${r.explanationViews?.length ? `<ul>${li(r.explanationViews)}</ul>` : ''}
${r.explanations.map((h) => `<h3>${esc(h.title)} <span class="tag">${esc(h.standing)}</span></h3>
${h.for.length ? `<p><b>For</b></p><ul>${li(h.for)}</ul>` : ''}${h.against.length ? `<p><b>Against</b></p><ul>${li(h.against)}</ul>` : ''}
${h.context.length ? `<p><b>Context, not counted</b></p><ul>${li(h.context)}</ul>` : ''}
${h.missing.length ? `<p><b>Would settle it</b></p><ul>${li(h.missing)}</ul>` : ''}`).join('')}
${r.hazards ? `<h2>Hazard screens <span class="tag">Experimental</span></h2>
${r.hazards.terrain ? `<p><b>Landslide-prone terrain:</b> ${esc(r.hazards.terrain.class)}</p><ul>${li(r.hazards.terrain.factors)}</ul>` : ''}
${r.hazards.road ? roadHtml(r.hazards.road, li) : ''}
<p class="muted">${esc(r.hazards.maturity)}. Terrain and position only: geology, soil and rainfall are not included.</p>` : ''}
<h2>Every value at this spot</h2>
<table><tr><th>Layer</th><th>Evidence</th><th>Value</th><th>Observation</th><th>Source file</th></tr>
${r.readings.map((x) => `<tr><td>${esc(x.layer)}</td><td>${esc(x.evidence)}</td><td>${x.value === null ? `<span class="muted">${esc(x.state)}</span>` : `${num(x.value)} ${esc(x.units === '1' ? '' : x.units ?? '')}`}</td><td>${esc(x.observation)}</td><td style="word-break:break-all">${esc(x.source)}</td></tr>`).join('')}</table>
<h2>Read this first</h2><ul>${li(r.notes)}</ul>
</body></html>`
}

export function save(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
