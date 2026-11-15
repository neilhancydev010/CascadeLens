import { useState } from 'react'
import type { LakeScenario, LakeSeries } from '../../types/manifest'
import { CountUp } from '../motion/CountUp'
import { assetUrl } from '../../services/manifest'
import { EvidenceTag } from '../explanations/EvidenceTag'

// "What if the dam breached?" Every number is computed by processing/src/cascade_lens/scenario.py from the NISAR lake area
// and the Copernicus terrain. Shown as ranges, because the published formulas disagree and the river's roughness is unknown.

const STOPS = [5, 10, 20, 30, 50, 75, 100]
const fmt = (n: number) => Math.round(n).toLocaleString('en-GB')
const sci = (x: number) => { const e = Math.floor(Math.log10(x)); return `${(x / 10 ** e).toFixed(3)}×10^${e}` }
const minutes = (m: number) => (m < 90 ? `${m} min` : `${(m / 60).toFixed(1).replace(/\.0$/, '')} h`)

function Profile({ s, at }: { s: LakeScenario; at: [number, number, number][] }) {
  const W = 320, H = 130, L = 34, R = 8, T = 10, B = 22
  const p = s.profile
  const k1 = p[p.length - 1][0]
  const zs = p.map((q) => q[1])
  const z0 = Math.floor(Math.min(...zs) / 500) * 500, z1 = Math.ceil(Math.max(...zs) / 500) * 500
  const x = (k: number) => L + (k / k1) * (W - L - R)
  const y = (z: number) => T + (1 - (z - z0) / (z1 - z0)) * (H - T - B)
  const line = p.map((q) => `${x(q[0]).toFixed(1)},${y(q[1]).toFixed(1)}`).join(' ')
  return (
    <figure className="lake-chart scenario-profile">
      <figcaption>Height of the valley floor along the route</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Valley floor drops from ${fmt(zs[0])} m at the lake to ${fmt(zs[zs.length - 1])} m after ${Math.round(k1)} km`}>
        {[z0, (z0 + z1) / 2, z1].map((v) => <g key={v}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="grid" /><text x={L - 4} y={y(v) + 3} textAnchor="end">{fmt(v)}</text></g>)}
        <polygon points={`${x(0)},${y(z0)} ${line} ${x(k1)},${y(z0)}`} className="range" />
        <polyline points={line} className="line" pathLength={1} />
        {at.map(([k], i) => (
          <g key={k} style={{ ['--i' as string]: i }}>
            <line x1={x(k)} x2={x(k)} y1={T} y2={H - B} className="tick" />
            <text x={x(k)} y={H - 8} textAnchor="middle">{k} km</text>
          </g>
        ))}
      </svg>
    </figure>
  )
}

// "Show the working": every input and formula with the chosen breach's numbers put in, so the panel can be checked on a calculator.
function Working({ s, c }: { s: LakeScenario; c: LakeScenario['scenarios'][number] }) {
  const [lo, mean, hi] = s.areaRangeKm2 ?? [s.lakeAreaKm2, s.lakeAreaKm2, s.lakeAreaKm2]
  const g = s.gammaNm3 ?? 9800
  const v = mean * 1e6 * c.breachM
  const pe = c.breachM * v * g
  const byArea = c.peaksByArea
  return (
    <details className="compare-more working">
      <summary>Show the working</summary>
      <p><EvidenceTag kind="simulation" /> Breach depth assumed. Everything else follows from the inputs below.</p>
      <dl className="facts">
        <div><dt>Lake area (NISAR)</dt><dd>{lo.toFixed(3)} / {mean.toFixed(3)} / {hi.toFixed(3)} km² (low / mean / high)</dd></div>
        <div><dt>Breach depth h</dt><dd>{c.breachM} m (assumed)</dd></div>
        <div><dt>Unit weight γ</dt><dd>{fmt(g)} N/m³</dd></div>
        <div><dt>Roughness n</dt><dd>{s.roughness[0]} to {s.roughness[1]}</dd></div>
      </dl>
      <ol className="working-steps">
        <li>V = A × h = {fmt(mean * 1e6)} m² × {c.breachM} m = <strong>{fmt(v)} m³</strong></li>
        <li>Popov (1991): Qp = 0.0048 × V^0.896 = 0.0048 × {fmt(v)}^0.896 = <strong>{fmt(c.peakM3s.popov)} m³/s</strong></li>
        <li>Costa and Schuster (1988): PE = h × V × γ = {c.breachM} × {fmt(v)} × {fmt(g)} = {sci(pe)} J; Qp = 0.0158 × PE^0.41 = <strong>{fmt(c.peakM3s.costa)} m³/s</strong></li>
        <li>Huggel et al. (2002), worst case: Qp = 0.00077 × V^1.017 = <strong>{fmt(c.peakM3s.huggel)} m³/s</strong></li>
        <li>Manning at each 500 m cross-section: v = R^(2/3) × S^(1/2) / n, R = area / (width + 2 × depth); each segment takes its length / max(v, {s.speedFloorMs ?? 0.3} m/s).</li>
      </ol>
      {byArea && (
        <table className="scenario-table">
          <caption>The lake-area range, carried through ({c.breachM} m breach, m³/s)</caption>
          <thead><tr><th>Area</th><th>Popov</th><th>Costa</th><th>Huggel</th></tr></thead>
          <tbody>{(['low', 'mean', 'high'] as const).map((k, i) => <tr key={k}><td>{[lo, mean, hi][i].toFixed(3)} km²</td><td>{fmt(byArea[k].popov)}</td><td>{fmt(byArea[k].costa)}</td><td>{fmt(byArea[k].huggel)}</td></tr>)}</tbody>
        </table>
      )}
      <p className="muted small">Likely peak range: the lower of Popov and Costa at the lowest area, {fmt(c.peakRange[0])} m³/s, to the higher at the highest area, {fmt(c.peakRange[1])} m³/s.{c.floors && ` Of ${c.floors.sections} cross-sections, the minimum slope of ${s.slopeFloor ?? 0.002} applies at ${c.floors.slope} and the minimum speed at ${c.floors.speedSlow}.`}</p>
      <p className="small">
        {s.sectionsCsv && <><a href={assetUrl(s.sectionsCsv)} download>Every cross-section (CSV)</a> · </>}
        <a href={assetUrl('data/working/scenario-check.xlsx')} download>Spreadsheet with live formulas (XLSX)</a>
      </p>
    </details>
  )
}

export function ScenarioPanel({ lake, onExit }: { lake: LakeSeries; onExit: () => void }) {
  const s = lake.scenario!
  const [bi, setBi] = useState(Math.min(1, s.scenarios.length - 1))
  const c = s.scenarios[bi]
  const rows = STOPS.map((k) => {
    const a = c.arrival.find((q) => q[0] >= k)
    const d = c.depthM.find((q) => q[0] >= k)
    return a && d ? { k, a, d } : null
  }).filter((r): r is NonNullable<typeof r> => r !== null)
  return (
    <section className="story compare-panel scenario-panel" aria-label="Dam-failure scenario">
      <header className="compare-head">
        <p className="label">What if · scenario</p>
        <h2>What if the {lake.name} dam failed?</h2>
        <p className="notice small"><strong>A scenario, not a prediction.</strong> Nobody can calculate whether or when the dam will fail. This works out what would follow if it did, from real measurements, with honest ranges. It is not a warning.</p>
      </header>
      <div className="tabs segmented" role="tablist" aria-label="How deep the breach is">
        {s.scenarios.map((q, i) => <button key={q.breachM} role="tab" aria-selected={i === bi} className={i === bi ? 'on' : ''} onClick={() => setBi(i)}>{q.breachM} m breach</button>)}
      </div>
      <p className="muted small">If a gap {c.breachM} m deep opened in the moraine, the top {c.breachM} m of the lake would drain. The lake area is NISAR's measurement, {s.lakeAreaKm2.toFixed(2)} km².</p>
      <dl className="facts">
        <div><dt>Water released</dt><dd><CountUp value={c.volumeM3 / 1e6} format={(v) => `about ${Math.round(v)} million m³`} /></dd></div>
        <div><dt>Peak flow at the dam</dt><dd><CountUp value={c.peakRange[0]} format={fmt} />–<CountUp value={c.peakRange[1]} format={fmt} /> m³/s</dd></div>
        <div className="wide"><dt>Worst case (upper limit of past floods)</dt><dd>up to {fmt(c.worstM3s)} m³/s</dd></div>
      </dl>
      <Profile s={s} at={rows.filter((r) => [10, 30, 50, 100].includes(r.k)).map((r) => [r.k, r.a[1], r.a[2]])} />
      <table className="scenario-table">
        <caption>When the water would arrive, along the {Math.round(s.routeKm)} km route</caption>
        <thead><tr><th>Distance</th><th>Arrives after</th><th>Water depth</th></tr></thead>
        <tbody>
          {rows.map(({ k, a, d }) => <tr key={k}><td>{k} km</td><td>{minutes(a[1])} to {minutes(a[2])}</td><td>{fmt(d[1])} to {fmt(d[2])} m</td></tr>)}
        </tbody>
      </table>
      {c.arrivalKinematic && (
        <p className="muted small"><strong>Sensitivity, not the default:</strong> if the front moved at the flood-wave speed (5/3 of the water speed) instead, every time would be 40% shorter, for example {(() => { const k = c.arrivalKinematic!.find((q) => q[0] >= 10); return k ? `${minutes(k[1])} to ${minutes(k[2])} at 10 km` : '' })()}. The method uses the water speed and never shrinks the peak downstream: the first makes times too late, the second too early.</p>
      )}
      <p className="muted small">The route follows the valley floor down the {lake.basin}. On the map, the blue area is the widest flooding of the 20 m case.</p>
      <Working s={s} c={c} />
      <details className="compare-more">
        <summary>How this is calculated</summary>
        <p><strong>Water:</strong> lake area from NISAR × breach depth. The lake walls are treated as vertical, so this slightly overestimates.</p>
        <p><strong>Peak flow:</strong> the likely range comes from {s.formulas.popov} and {s.formulas.costa}, two published formulas fitted to past dam failures. {s.formulas.huggel} gives the worst case.</p>
        <p><strong>Speed and depth:</strong> the route is cut by a cross-section every {s.sectionEveryM} m through the {s.dem.startsWith('Copernicus') ? 'Copernicus 30 m terrain model (averaged to 60 m)' : 'terrain model'}. In each one, Manning's equation finds the depth and speed that carry the peak flow, with river roughness from {s.roughness[0]} to {s.roughness[1]}. The fastest time pairs the highest flow with the smoothest channel; the slowest pairs the lowest flow with the roughest.</p>
        <p><strong>Not included:</strong> the flood shrinking as it spreads (which makes far-downstream times too early and depths too high), the flood wave moving faster than the water (which makes every time too late), rock and mud carried by the water, landslides it could trigger, and bridges or dams in the way. The two timing errors pull in opposite directions, so the times are not reliably early or late.</p>
        <p className="notice small">Real hazard work uses a full flood model calibrated on surveyed river channels. This is a first estimate to show what the data can do.</p>
      </details>
      <footer><button className="ghost" onClick={onExit}>Close scenario</button></footer>
    </section>
  )
}
