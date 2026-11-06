import type { Layer } from '../../types/manifest'
import { unitLabel } from '../../services/manifest'

const CATEGORY_LIMIT = 8

function fmt(v: number | undefined) {
  if (v === undefined) return '—'
  return Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2)
}

function Ramp({ stops, low, high }: { stops: string[]; low: string; high: string }) {
  return (
    <>
      <div className="ramp" style={{ background: `linear-gradient(90deg, ${stops.join(',')})` }} />
      <div className="ramp-labels"><span>{low}</span><span>{high}</span></div>
    </>
  )
}

export function Legend({ layer, references }: { layer: Layer | undefined; references: Layer[] }) {
  const l = layer?.legend
  const rasters = references.filter((r) => r.legend)
  const vectors = references.filter((r) => r.vector?.color)
  if (!l && !rasters.length && !vectors.length) return null
  const unit = unitLabel(l?.unit)
  const labels = l?.labels ?? []
  return (
    <section className="legend" aria-label="Map legend">
      {layer && l && (
        <div>
          <p className="legend-title">{layer.name}{unit ? ` (${unit})` : ''}</p>
          {l.keys ? (
            <ul className="swatches">{l.keys.map((k) => <li key={k.label}><i style={{ background: k.color }} />{k.label}</li>)}</ul>
          ) : l.type === 'continuous' ? <Ramp stops={l.stops} low={l.lowLabel ?? fmt(l.min)} high={l.highLabel ?? fmt(l.max)} /> : (
            <ul className="swatches">
              {labels.slice(0, CATEGORY_LIMIT).map((c) => (
                <li key={c}><i style={{ background: l.stops[c % l.stops.length] }} />{c === 0 ? 'Not reliably unwrapped' : `Component ${c}`}</li>
              ))}
              {labels.length > CATEGORY_LIMIT && <li>and {labels.length - CATEGORY_LIMIT} more</li>}
            </ul>
          )}
        </div>
      )}
      {rasters.map((r) => <div key={r.id}><p className="legend-title">{r.name}</p><Ramp stops={r.legend!.stops} low={r.legend!.lowLabel ?? ''} high={r.legend!.highLabel ?? ''} /></div>)}
      {vectors.length > 0 && (
        <ul className="swatches">
          {vectors.map((r) => (
            <li key={r.id}><i className={`sw-${r.vector!.type}`} style={{ background: r.vector!.color }} />{r.name}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
