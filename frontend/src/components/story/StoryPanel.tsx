import type { StoryStep } from '../../data/story'
import type { Manifest } from '../../types/manifest'
import { Bars, type BarGroup } from '../charts/Charts'

interface Props {
  steps: StoryStep[]
  index: number
  manifest: Manifest
  onGo: (i: number) => void
  onExit: () => void
}

// Coherence inside the mapped extent against the ring around it, straight from the analysis file.
export function coherenceGroups(m: Manifest): BarGroup[] {
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

export function StoryPanel({ steps, index, manifest, onGo, onExit }: Props) {
  const step = steps[index]
  const last = index === steps.length - 1
  const bars = step.layerId.endsWith('gunw-coherence') ? coherenceGroups(manifest) : []
  return (
    <section className="story" aria-label="Rasuwa story" aria-live="polite">
      <ol className="progress" aria-label="Story steps">
        {steps.map((s, i) => (
          <li key={s.id} className={i < index ? 'done' : i === index ? 'now' : ''}>
            <button className="progress-step" onClick={() => onGo(i)} aria-current={i === index ? 'step' : undefined} aria-label={`Go to step ${i + 1}: ${s.title}`}><i />{s.title}</button>
          </li>
        ))}
      </ol>
      <p className="eyebrow">Step {index + 1} of {steps.length} · The mountain-to-river story</p>
      <div className={`story-body ${bars.length ? 'with-chart' : ''}`}>
        <div>
          <h2>{index + 1}. {step.title}</h2>
          {step.paragraphs.map((p) => <p key={p}>{p}</p>)}
        </div>
        {bars.length > 0 && <Bars title="Signal quality (coherence: 0 = noisy, 1 = stable)" groups={bars} />}
      </div>
      <footer>
        <button className="ghost" onClick={onExit}>Exit story</button>
        <span className="grow" />
        <button onClick={() => onGo(index - 1)} disabled={index === 0}>Back</button>
        {last ? <button className="primary" onClick={onExit}>Explore the map</button>
          : <button className="primary" onClick={() => onGo(index + 1)}>Next: {steps[index + 1].title.replace(/^The /, 'the ')} →</button>}
      </footer>
    </section>
  )
}
