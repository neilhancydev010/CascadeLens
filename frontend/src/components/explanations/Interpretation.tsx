import { lazy, memo, Suspense } from 'react'
import type { Layer } from '../../types/manifest'
import { acquisitionLabel, isUsable, posting, STATUS_LABEL, unitLabel } from '../../services/manifest'
import { explanationFor } from '../../data/explanations'
import { Donut } from '../charts/Charts'

const HistogramChart = lazy(() => import('../charts/LibraryCharts').then((m) => ({ default: m.HistogramChart })))

function Histogram({ layer }: { layer: Layer }) {
  const h = layer.stats?.histogram
  if (!h) return null
  const data = h.counts.map((count, i) => ({ value: Number(h.edges[i].toFixed(2)), count }))
  const unit = layer.displayDb ? 'dB' : `${unitLabel(layer.units)}${layer.displayRelative ? ', relative to frame median' : ''}`
  return (
    <figure className="histogram card">
      <figcaption>Distribution of valid pixels{unit ? ` (${unit})` : ''}</figcaption>
      <Suspense fallback={<div style={{ height: 84 }} />}><HistogramChart data={data} /></Suspense>
    </figure>
  )
}

const RADAR = ['gunw', 'goff', 'gcov']

// Both pies use only manifest figures: pixel fractions per frame, and the status of every radar layer.
function AtAGlance({ layer, layers }: { layer: Layer; layers: Layer[] }) {
  const pct = (x: number) => Math.round(x * 100)
  const frames = layer.sources.filter((s) => s.validFraction !== undefined)
  const radar = layer.mission !== 'NISAR' ? [] : layers.filter((l) => l.mission === 'NISAR' && RADAR.includes(l.category))
  const ready = radar.filter(isUsable).length
  const notDownloaded = radar.filter((l) => l.status === 'catalogued').length
  const other = radar.length - ready - notDownloaded
  if (!frames.length && !radar.length) return null
  return (
    <section className="glance">
      <h3 className="label">At a glance</h3>
      {frames.map((s) => {
        const valid = pct(s.validFraction!)
        const masked = pct(s.maskedFraction ?? 0)
        return (
          <Donut key={s.granule} title={`Usable pixels${s.frame ? `, frame ${s.frame}` : ''}`} centre={`${valid}%`} note="%"
            slices={[{ label: 'Valid', value: valid, color: 'var(--accent)' }, { label: 'Masked', value: masked, color: 'var(--amber)' }, { label: 'No data', value: Math.max(0, 100 - valid - masked), color: 'var(--grey)' }]} />
        )
      })}
      {radar.length > 0 && (
        <Donut title="Radar layers" centre={`${ready}/${radar.length}`}
          slices={[{ label: 'Ready', value: ready, color: 'var(--accent)' }, { label: 'Not downloaded', value: notDownloaded, color: 'var(--coral)' }, ...(other ? [{ label: 'In preparation', value: other, color: 'var(--amber)' }] : [])]} />
      )}
    </section>
  )
}

function Question({ q, a, open }: { q: string; a: string; open?: boolean }) {
  return <details className="question" open={open}><summary><h3>{q}</h3></summary><p>{a}</p></details>
}

export const Interpretation = memo(function Interpretation({ layer, layers }: { layer: Layer; layers: Layer[] }) {
  const e = explanationFor(layer)
  const unit = layer.unitsNote ?? unitLabel(layer.units)
  const tiles: [string, string][] = [
    ['Observation', acquisitionLabel(layer)],
    ...(layer.orbitDirection ? [['Orbit', `${layer.orbitDirection.toLowerCase()}, Track ${layer.track}, frames ${layer.frames.join('/')}`] as [string, string]] : []),
    ...(unit ? [['Units', unit] as [string, string]] : []),
    ...(layer.postingM ? [['Native posting', posting(layer)] as [string, string]] : []),
    ['Status', STATUS_LABEL[layer.status]],
  ]
  return (
    <>
      <dl className="facts">
        {tiles.map(([k, v]) => <div key={k} className={v.length > 40 ? 'wide' : undefined}><dt>{k}</dt><dd>{v}</dd></div>)}
      </dl>
      {layer.statusReason && <p className="notice">{layer.statusReason}</p>}
      <AtAGlance layer={layer} layers={layers} />
      <Histogram layer={layer} />
      <section className="questions">
        <Question q="What am I seeing?" a={e.what} open />
        <Question q="What does it measure?" a={e.measures} />
        <Question q="What should I inspect?" a={e.inspect} />
        <Question q="What does it establish?" a={e.establishes} />
      </section>
      <section className="callout">
        <h3 className="label">Limits</h3>
        <ul className="limits">{layer.limitations.map((t) => <li key={t}>{t}</li>)}</ul>
      </section>
      <section className="source">
        <h3 className="label">Source</h3>
        <p className="attribution">{layer.attribution}</p>
        {layer.page && <p className="attribution break">{layer.page}</p>}
        <p className="attribution">Product maturity: {layer.productMaturity}{layer.crs ? ` · ${layer.crs}` : ''}</p>
        {layer.sourceGranules.length > 0 && (
          <details>
            <summary>Source granules ({layer.sourceGranules.length})</summary>
            <ul className="granules">{layer.sourceGranules.map((g) => <li key={g} className="break">{g}</li>)}</ul>
          </details>
        )}
        {layer.processingHistory && (
          <details>
            <summary>Processing history</summary>
            <pre className="break">{JSON.stringify(layer.processingHistory, null, 1)}</pre>
          </details>
        )}
      </section>
    </>
  )
})
