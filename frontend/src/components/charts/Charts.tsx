// Small SVG charts in the CascadeLens palette. No library: they must work offline and under a strict CSP.

export interface Slice { label: string; value: number; color: string }

export function Donut({ title, slices, centre, note }: { title: string; slices: Slice[]; centre: string; note?: string }) {
  const total = slices.reduce((s, x) => s + x.value, 0) || 1
  const r = 30
  const c = 2 * Math.PI * r
  let offset = 0
  return (
    <figure className="donut-card">
      <svg viewBox="0 0 80 80" width="80" height="80" role="img" aria-label={`${title}: ${slices.map((s) => `${s.label} ${s.value}`).join(', ')}`}>
        <circle cx="40" cy="40" r={r} fill="none" stroke="var(--raised)" strokeWidth="11" />
        {slices.filter((s) => s.value > 0).map((s) => {
          const len = (s.value / total) * c
          const el = <circle key={s.label} cx="40" cy="40" r={r} fill="none" stroke={s.color} strokeWidth="11" strokeDasharray={`${len} ${c - len}`} strokeDashoffset={c - offset} transform="rotate(-90 40 40)" />
          offset += len
          return el
        })}
        <text x="40" y="44" textAnchor="middle" className="donut-centre">{centre}</text>
      </svg>
      <figcaption>
        <strong>{title}</strong>
        <ul>{slices.map((s) => <li key={s.label}><i style={{ background: s.color }} />{s.label}<b>{s.value}{note}</b></li>)}</ul>
      </figcaption>
    </figure>
  )
}

export interface BarGroup { label: string; bars: { label: string; value: number; color: string }[] }

export function Bars({ title, groups, max = 1 }: { title: string; groups: BarGroup[]; max?: number }) {
  return (
    <figure className="bars">
      <figcaption>{title}</figcaption>
      {groups.map((g) => (
        <div className="bar-group" key={g.label}>
          <span className="bar-group-label">{g.label}</span>
          {g.bars.map((b) => (
            <div className="bar-row" key={b.label}>
              <span>{b.label}</span>
              <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.min(100, (b.value / max) * 100)}%`, background: b.color }} /></div>
              <b>{b.value.toFixed(2)}</b>
            </div>
          ))}
        </div>
      ))}
    </figure>
  )
}
