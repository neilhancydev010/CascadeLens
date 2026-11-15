import { Fragment, type CSSProperties } from 'react'
import type { StoryStep } from '../../data/story'
import type { Manifest } from '../../types/manifest'
import { Bars, type BarGroup } from '../charts/Charts'
import { LakeChart } from '../compare/ComparePanel'

interface Props {
  steps: StoryStep[]
  index: number
  manifest: Manifest
  onGo: (i: number) => void
  onExit: () => void
}

// Coherence inside the mapped extent against the ring around it, straight from the analysis file.
const short = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })

export function coherenceGroups(m: Manifest): BarGroup[] {
  const cs = m.controlSeries
  if (cs?.pairs.length) {
    return cs.pairs.map((p) => ({
      label: `${short(p.pair[0])} – ${short(p.pair[1])}${p.pair[1] <= cs.eventDate ? ' (before)' : p.pair[0] < cs.eventDate ? ' (across the event)' : ' (after)'}`,
      bars: [
        { label: 'Inside the slide', value: p.inside, color: 'var(--coral)' },
        { label: 'Around it', value: p.outside, color: 'var(--accent)' },
      ],
    }))
  }
  return Object.entries(m.analysis?.['pair-a']?.frames ?? {}).flatMap(([name, f]) => {
    const inside = f.zones['gunw-coherence']?.['mapped extent']?.median
    const outside = f.zones['gunw-coherence']?.['1 km ring outside extent']?.median
    return inside == null || outside == null ? [] : [{
      label: `Frame ${Number(name.slice(1))}`,
      bars: [
        { label: 'Inside the slide', value: inside, color: 'var(--coral)' },
        { label: 'Around it', value: outside, color: 'var(--accent)' },
      ],
    }]
  })
}

const OBS_ZONES: [string, string][] = [['vector:unosat_detachment_zone.geojson', 'Detachment zone'], ['vector:unosat_mudflow_extent.geojson', 'Mapped mudflow'], ['bookmark:bhote-koshi', 'Bhote Koshi corridor'], ['bookmark:trishuli', 'Trishuli corridor']]

export function observabilityGroups(m: Manifest): BarGroup[] {
  const o = m.observability
  if (!o) return []
  return OBS_ZONES.flatMap(([id, label]) => {
    const d = o.zones.disturbance?.[id]?.percent?.Usable
    const mv = o.zones.movement?.[id]?.percent?.Usable
    return d == null || mv == null ? [] : [{ label, bars: [
      { label: 'See a change', value: d, color: 'var(--accent)' },
      { label: 'Measure movement', value: mv, color: 'var(--coral)' },
    ] }]
  })
}

// The step title becomes a two-line headline: the first line in the serif face with one italic word, the second in the sans face.
// A comma decides the break when there is one; otherwise the words are shared out as evenly as they can be.
export function splitTitle(title: string): [string[], string[]] {
  const words = title.split(' ')
  if (words.length < 2) return [words, []]
  const comma = words.findIndex((w, i) => i < words.length - 1 && /[,:;]$/.test(w))
  if (comma >= 0) return [words.slice(0, comma + 1), words.slice(comma + 1)]
  let best = 1
  let gap = Infinity
  for (let i = 1; i < words.length; i++) {
    const g = Math.abs(words.slice(0, i).join(' ').length - words.slice(i).join(' ').length)
    if (g < gap) { gap = g; best = i }
  }
  return [words.slice(0, best), words.slice(best)]
}

function Headline({ number, title }: { number: number; title: string }) {
  const [top, bottom] = splitTitle(title)
  const chars = Math.max(top.join(' ').length * 1.02, bottom.join(' ').length, 8)
  let i = 0
  const word = (w: string, italic = false) => {
    const style = { '--i': i++ } as CSSProperties
    return italic ? <em className="word" style={style}>{w}</em> : <span className="word" style={style}>{w}</span>
  }
  return (
    <h2 className="headline" aria-label={`${number}. ${title}`} style={{ '--chars': chars } as CSSProperties}>
      <span className="line serif">{top.map((w, k) => <Fragment key={k}>{k > 0 && ' '}{word(w, k === top.length - 1)}</Fragment>)}</span>
      {bottom.length > 0 && <>{' '}<span className="line sans">{bottom.map((w, k) => <Fragment key={k}>{k > 0 && ' '}{word(w)}</Fragment>)}</span></>}
    </h2>
  )
}

export function StoryPanel({ steps, index, manifest, onGo, onExit }: Props) {
  const step = steps[index]
  const last = index === steps.length - 1
  const bars = step.layerId.endsWith('gunw-coherence') ? coherenceGroups(manifest) : []
  const chart = step.chart === 'lake' && manifest.lake
  const obsBars = step.chart === 'observability' ? observabilityGroups(manifest) : []
  const name = manifest.lake ? `The ${manifest.lake.name} story` : 'The mountain-to-river story'
  return (
    <section className="story guided" aria-label={name} aria-live="polite">
      <div className="story-hero">
        <p className="kicker"><i className="dot" aria-hidden="true" />Step {index + 1} <span className="pill">of {steps.length}</span> <span className="kicker-name">{name}</span></p>
        <Headline key={step.id} number={index + 1} title={step.title} />
      </div>
      <div className="story-card" key={step.id}>
        <ol className="points">{step.paragraphs.map((p) => <li key={p}><p>{p}</p></li>)}</ol>
        {chart && <LakeChart lake={manifest.lake!} />}
        {obsBars.length > 0 && <Bars title="Share of ground the radar can judge (%)" groups={obsBars} max={100} unit="%" />}
        {bars.length > 0 && <Bars title="Signal quality (coherence: 0 = noisy, 1 = stable)" groups={bars} />}
        {step.sources && <p className="muted small story-sources">{step.sources}</p>}
      </div>
      <div className="story-nav">
        <ol className="progress" aria-label="Story steps">
          {steps.map((s, i) => (
            <li key={s.id} className={i < index ? 'done' : i === index ? 'now' : ''}>
              <button className="progress-step" onClick={() => onGo(i)} aria-current={i === index ? 'step' : undefined} aria-label={`Go to step ${i + 1}: ${s.title}`}><i />{s.title}</button>
            </li>
          ))}
        </ol>
        <footer>
          {last ? <button className="primary" onClick={onExit}>Explore the map</button>
            : <button className="primary" onClick={() => onGo(index + 1)}><span className="next-label">Next: {steps[index + 1].title.replace(/^The /, 'the ')}</span></button>}
          <button onClick={() => onGo(index - 1)} disabled={index === 0}>Back</button>
          <span className="grow" />
          <button className="ghost" onClick={onExit}>Exit story</button>
        </footer>
      </div>
    </section>
  )
}
