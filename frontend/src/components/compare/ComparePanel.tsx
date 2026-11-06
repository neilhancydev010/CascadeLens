import { useState } from 'react'
import type { LakePoint, LakeSeries } from '../../types/manifest'
import { assetUrl, formatDate } from '../../services/manifest'
import { CountUp } from '../motion/CountUp'

// Before/after swipe over the same radar clip, and the lake size measured on every date. Both come from lake.py.

const km2 = (x: number) => `${x.toFixed(2)} km²`
const mode = (p: LakePoint) => `${p.polarization}-pol, ${p.nativePostingM} m`

// Matches the Colour radar legend written by lake.py
export const COLOUR_KEY = [
  { color: '#000000', label: 'Black: calm water, or radar shadow' },
  { color: '#6b4fd8', label: 'Purple: smooth bare rock, ice, snow' },
  { color: '#b8d23a', label: 'Yellow-green: rough moraine, boulders, debris' },
  { color: '#fff6b0', label: 'Bright blobs: steep slopes facing the radar (distorted)' },
]

function Swipe({ lake, before, after, showEdge }: { lake: LakeSeries; before: LakePoint; after: LakePoint; showEdge: boolean }) {
  const [split, setSplit] = useState(50)
  const [w, h] = lake.imageSize
  return (
    <div className="swipe">
      <div className="swipe-frame" style={{ aspectRatio: `${w} / ${h}` }}>
        <img src={assetUrl(after.image)} alt={`Radar image of ${lake.name} on ${formatDate(after.date)}`} draggable={false} />
        <img src={assetUrl(before.image)} alt={`Radar image of ${lake.name} on ${formatDate(before.date)}`} draggable={false} style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }} />
        {showEdge && (
          <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
            <path d={after.outline} className="edge after" />
            <path d={before.outline} className="edge before" />
          </svg>
        )}
        <div className="swipe-line" style={{ left: `${split}%` }} aria-hidden="true"><span /></div>
        <span className="swipe-tag tag-before">{formatDate(before.date)}</span>
        <span className="swipe-tag tag-after">{formatDate(after.date)}</span>
      </div>
      <input className="swipe-range" type="range" min={0} max={100} value={split} aria-label="Move the divider between the two dates" onChange={(e) => setSplit(Number(e.target.value))} />
    </div>
  )
}

export function LakeChart({ lake, highlight }: { lake: LakeSeries; highlight?: string[] }) {
  const s = lake.series
  const lo = Math.min(...s.map((p) => p.lowKm2))
  const hi = Math.max(...s.map((p) => p.highKm2))
  const pad = Math.max(0.1, (hi - lo) * 0.4)
  const [y0, y1] = [Math.max(0, lo - pad), hi + pad]
  const t = s.map((p) => Date.parse(p.date))
  const span = Math.max(1, t[t.length - 1] - t[0])
  const W = 300, H = 120, L = 34, R = 10, T = 10, B = 22
  const x = (i: number) => L + ((t[i] - t[0]) / span) * (W - L - R)
  const y = (v: number) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B)
  const ticks = [y0, (y0 + y1) / 2, y1]
  const band = [...s.map((p, i) => `${x(i)},${y(p.highKm2)}`), ...s.map((p, i) => `${x(i)},${y(p.lowKm2)}`).reverse()].join(' ')
  return (
    <figure className="lake-chart">
      <figcaption>Lake size on each radar date</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Lake area: ${s.map((p) => `${formatDate(p.date)} ${km2(p.areaKm2)}`).join(', ')}`}>
        {ticks.map((v) => <g key={v}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="grid" /><text x={L - 4} y={y(v) + 3} textAnchor="end">{v.toFixed(1)}</text></g>)}
        <polygon points={band} className="range" />
        <polyline points={s.map((p, i) => `${x(i)},${y(p.areaKm2)}`).join(' ')} className="line" pathLength={1} />
        {s.map((p, i) => (
          <g key={p.date} style={{ ['--i' as string]: i }}>
            <circle cx={x(i)} cy={y(p.areaKm2)} r={highlight?.includes(p.date) ? 5 : 3.5} className={highlight?.includes(p.date) ? 'dot on' : 'dot'} />
            <text x={x(i)} y={H - 6} textAnchor={i === 0 ? 'start' : i === s.length - 1 ? 'end' : 'middle'}>{formatDate(p.date).replace(/ \d{4}$/, '')}</text>
          </g>
        ))}
      </svg>
      <p className="muted small"><i className="key line" />Measured area, km² <i className="key range" />Method range</p>
    </figure>
  )
}

function verdict(a: LakePoint, b: LakePoint) {
  const d = b.areaKm2 - a.areaKm2
  const noise = Math.max((a.highKm2 - a.lowKm2) / 2, (b.highKm2 - b.lowKm2) / 2)
  const pct = (Math.abs(d) / a.areaKm2) * 100
  if (Math.abs(d) <= noise) {
    return { tone: 'teal', head: 'No change the radar can detect', body: `The area moved by ${Math.abs(d).toFixed(2)} km² (${pct.toFixed(1)}%), which is inside the measurement's own range of about ±${noise.toFixed(2)} km². The lake edge stayed in the same place.` }
  }
  return { tone: 'coral', head: d > 0 ? 'The lake grew' : 'The lake shrank', body: `By ${Math.abs(d).toFixed(2)} km² (${pct.toFixed(1)}%), more than the measurement's range of about ±${noise.toFixed(2)} km². Check the edges in the image: shadow and wind on the water can also change the outline.` }
}

export function ComparePanel({ lake, onExit }: { lake: LakeSeries; onExit: () => void }) {
  const s = lake.series
  const [ai, setAi] = useState(0)
  const [bi, setBi] = useState(s.length - 1)
  const [showEdge, setShowEdge] = useState(true)
  const a = s[ai], b = s[bi]
  const v = verdict(a, b)
  const days = Math.round((Date.parse(b.date) - Date.parse(a.date)) / 86400000)
  const pick = (label: string, value: number, set: (i: number) => void) => (
    <label className="select">{label}
      <select value={value} onChange={(e) => set(Number(e.target.value))}>
        {s.map((p, i) => <option key={p.date} value={i}>{formatDate(p.date)}</option>)}
      </select>
    </label>
  )
  return (
    <section className="story compare-panel" aria-label="Compare dates">
      <header className="compare-head">
        <p className="label">Compare dates</p>
        <h2>{lake.name}: before and after</h2>
        <p className="muted small">Drag the divider. Left is the earlier date, right the later one. Same NISAR radar track, same viewing angle.{lake.imageMetres && ` The picture is about ${(lake.imageMetres[0] / 1000).toFixed(1)} by ${(lake.imageMetres[1] / 1000).toFixed(1)} km.`}</p>
      </header>
      <div className="compare-picks">
        {pick('Before', ai, setAi)}
        {pick('After', bi, setBi)}
        <label className="check"><input type="checkbox" checked={showEdge} onChange={(e) => setShowEdge(e.target.checked)} />Lake edge</label>
      </div>
      <Swipe lake={lake} before={a} after={b} showEdge={showEdge} />
      <ul className="colour-key" aria-label="Colour key">
        {COLOUR_KEY.map((k) => <li key={k.label}><i style={{ background: k.color }} />{k.label}</li>)}
      </ul>
      <div className={`verdict ${v.tone}`}>
        <strong>{v.head}</strong>
        <p>{v.body}</p>
      </div>
      <dl className="facts">
        <div><dt>{formatDate(a.date)}</dt><dd><CountUp value={a.areaKm2} format={km2} /></dd></div>
        <div><dt>{formatDate(b.date)}</dt><dd><CountUp value={b.areaKm2} format={km2} /></dd></div>
        <div><dt>Time between</dt><dd><CountUp value={days} format={(v) => `${Math.round(v)} days`} /></dd></div>
        <div className="wide"><dt>Radar modes</dt><dd>{a.polarization === b.polarization ? `Same mode (${mode(a)}): the fairest comparison` : `Different modes (${mode(a)} and ${mode(b)}). Both are compared on a 20 m grid, but for the fairest test pick two dates in the same mode.`}</dd></div>
      </dl>
      <LakeChart lake={lake} highlight={[a.date, b.date]} />
      <details className="compare-more">
        <summary>What am I looking at?</summary>
        <p><strong>What:</strong> NISAR's L-band radar sees through cloud and works at night. Calm water reflects the pulse away from the satellite, so the lake is near black. Smooth surfaces send the pulse straight back and look purple. Rough, jumbled ground scrambles it and looks yellow-green.</p>
        <p><strong>Where:</strong> {lake.name} drains into the {lake.basin}. A sudden outburst from a lake like this would travel down that valley.</p>
        <p><strong>Why it matters:</strong> a growing glacial lake holds more water behind its moraine dam. Watching its size, date by date and through monsoon cloud, is one early sign people use to judge outburst risk.</p>
        <p><strong>How it is measured:</strong> {lake.method}</p>
        {lake.published && <p><strong>Check:</strong> {lake.published}</p>}
        <p className="notice small">Provisional NISAR data. These are real acquisition dates, not live monitoring. This is not a flood warning.</p>
      </details>
      <footer><button className="ghost" onClick={onExit}>Close compare</button></footer>
    </section>
  )
}
