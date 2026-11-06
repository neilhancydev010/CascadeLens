import { useState } from 'react'
import type { LakeScenario, LakeSeries } from '../../types/manifest'
import { CountUp } from '../motion/CountUp'

// "What if the dam breached?" Every number is computed by processing/src/cascade_lens/scenario.py from the NISAR lake area
// and the Copernicus terrain. Shown as ranges, because the published formulas disagree and the river's roughness is unknown.

const STOPS = [5, 10, 20, 30, 50, 75, 100]
const fmt = (n: number) => Math.round(n).toLocaleString('en-GB')
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
      <p className="muted small">The route follows the valley floor down the {lake.basin}. On the map, the blue area is the widest flooding of the 20 m case.</p>
      <details className="compare-more">
        <summary>How this is calculated</summary>
        <p><strong>Water:</strong> lake area from NISAR × breach depth. The lake walls are treated as vertical, so this slightly overestimates.</p>
        <p><strong>Peak flow:</strong> the likely range comes from {s.formulas.popov} and {s.formulas.costa}, two published formulas fitted to past dam failures. {s.formulas.huggel} gives the worst case.</p>
        <p><strong>Speed and depth:</strong> the route is cut by a cross-section every {s.sectionEveryM} m through the {s.dem.startsWith('Copernicus') ? 'Copernicus 30 m terrain model (averaged to 60 m)' : 'terrain model'}. In each one, Manning's equation finds the depth and speed that carry the peak flow, with river roughness from {s.roughness[0]} to {s.roughness[1]}. The fastest time pairs the highest flow with the smoothest channel; the slowest pairs the lowest flow with the roughest.</p>
        <p><strong>Not included:</strong> the flood shrinking as it spreads (so times are on the early, cautious side, and far-downstream depths too high), rock and mud carried by the water, landslides it could trigger, and bridges or dams in the way.</p>
        <p className="notice small">Real hazard work uses a full flood model calibrated on surveyed river channels. This is a first estimate to show what the data can do.</p>
      </details>
      <p className="muted small"><strong>Next:</strong> a forecast of the lake's size in 2030 and 2040, once the yearly images are in.</p>
      <footer><button className="ghost" onClick={onExit}>Close scenario</button></footer>
    </section>
  )
}
