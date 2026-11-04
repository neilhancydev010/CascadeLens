import type { Bookmark, Layer, Manifest, ObservationGroup } from '../../types/manifest'
import { formatDate, isUsable, STATUS_LABEL } from '../../services/manifest'

export type EvidenceView = 'gunw' | 'goff' | 'gcov'

const VIEWS: { id: EvidenceView; label: string; hint: string }[] = [
  { id: 'gunw', label: 'InSAR', hint: 'Phase and coherence' },
  { id: 'goff', label: 'Pixel offsets', hint: 'Image-feature shifts' },
  { id: 'gcov', label: 'Snapshots', hint: 'Single-date backscatter' },
]

interface Props {
  manifest: Manifest
  group: ObservationGroup | undefined
  view: EvidenceView
  activeId: string
  step: number
  onStep: (i: number) => void
  hasStory: boolean
  layerVisible: boolean
  bookmarkId: string | null
  opacity: number
  showTerrain: boolean
  showMask: boolean
  overlayId: string
  referenceIds: string[]
  storyActive: boolean
  simActive: boolean
  canSimulate: boolean
  onSimulate: () => void
  onBookmark: (b: Bookmark) => void
  onGroup: (id: string) => void
  onView: (v: EvidenceView) => void
  onLayer: (id: string) => void
  onLayerVisible: (v: boolean) => void
  onOpacity: (v: number) => void
  onTerrain: (v: boolean) => void
  onMask: (v: boolean) => void
  onOverlay: (id: string) => void
  onReference: (id: string, on: boolean) => void
  onAbout: (id: string) => void
  onStory: () => void
}

function GroupOption({ g, selected, onSelect }: { g: ObservationGroup; selected: boolean; onSelect: () => void }) {
  // The primary pair stays selectable so its catalogue facts remain readable; others open only once validated.
  const locked = !g.available && !selected
  return (
    <label className={`option ${selected ? 'on' : ''} ${locked ? 'locked' : ''}`}>
      <input type="radio" name="observation" checked={selected} disabled={locked} onChange={onSelect} />
      <span>
        <strong>{g.label}</strong>
        <small>{g.direction.toLowerCase()} · Track {g.track} · Frames {g.frames.join('/')}</small>
        {!g.available && <small className="why">Not validated yet: {g.statusReason ?? 'no prepared data.'}</small>}
      </span>
    </label>
  )
}

function LayerRow({ layer, active, onSelect }: { layer: Layer; active: boolean; onSelect: () => void }) {
  const usable = isUsable(layer)
  const stops = layer.legend?.stops
  return (
    <label className={`option compact ${active ? 'on' : ''} ${usable ? '' : 'locked'}`}>
      <input type="radio" name="layer" checked={active} disabled={!usable} onChange={onSelect} />
      <i className="swatch" style={stops ? { background: `linear-gradient(90deg, ${stops.join(',')})` } : undefined} />
      <span>{layer.name}<small className={`status status-${layer.status}`}>{layer.category === 'gridded' && !usable ? layer.statusReason : STATUS_LABEL[layer.status]}</small></span>
    </label>
  )
}

const Play = () => <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M4 2.5v11l9-5.5z" fill="currentColor" /></svg>

export function LeftPanel(p: Props) {
  const { manifest: m, group, view } = p
  const pairs = m.groups.filter((g) => g.kind === 'pair')
  const snaps = m.groups.filter((g) => g.kind === 'snapshot')
  const shown = view === 'gcov' ? snaps : pairs
  const layers = m.layers.filter((l) => group && l.groupId === group.id && (l.category === view || l.previewOf === view))
  const gridded = m.layers.filter((l) => l.category === 'gridded')
  const terrain = m.layers.find((l) => l.category === 'terrain')
  const refs = m.layers.filter((l) => l.category === 'reference' && isUsable(l))
  const missions = [...new Set(refs.map((r) => r.mission))]
  const active = m.layers.find((l) => l.id === p.activeId)
  const overlays = (active?.qualityLayerIds ?? []).map((id) => m.layers.find((l) => l.id === id)).filter((l): l is Layer => Boolean(l && isUsable(l)))
  const canMask = Boolean(active?.sources.some((s) => s.maskTiles))
  const steps = active?.timeSteps
  return (
    <div className="panel-body">
      <section className="case-head">
        <p className="label">Case study</p>
        <h2 className="case">{m.caseStudy.name}</h2>
        <p className="muted small">{p.hasStory ? 'Reported event' : 'Data date'}: {formatDate(m.caseStudy.eventDate)}. A retrospective evidence explorer, not a warning service.</p>
        {(p.hasStory || p.canSimulate) && (
          <div className="story-cta">
            {p.hasStory && <p><strong>New here?</strong> Walk through the event in 4 steps.</p>}
            {p.hasStory && <button className="primary" onClick={p.onStory} disabled={p.storyActive}><Play />Start the guided story</button>}
            {p.canSimulate && <button onClick={p.onSimulate} disabled={p.simActive}>Try the simulations</button>}
          </div>
        )}
      </section>

      <section>
        <h3 className="label">Jump to</h3>
        <div className="chips places">
          {m.bookmarks.map((b) => (
            <button key={b.id} title={b.basis} aria-pressed={p.bookmarkId === b.id} className={p.bookmarkId === b.id ? 'on' : ''} onClick={() => p.onBookmark(b)}>{b.name}</button>
          ))}
        </div>
      </section>

      {gridded.length > 0 && (
        <section>
          <h3 className="label">Variables</h3>
          {gridded.map((l) => <LayerRow key={l.id} layer={l} active={l.id === p.activeId} onSelect={() => p.onLayer(l.id)} />)}
        </section>
      )}

      {group && <section>
        <h3 className="label">Radar evidence</h3>
        <div className="tabs segmented" role="tablist" aria-label="Evidence view">
          {VIEWS.map((v) => (
            <button key={v.id} role="tab" aria-selected={view === v.id} title={v.hint} className={view === v.id ? 'on' : ''} onClick={() => p.onView(v.id)}>{v.label}</button>
          ))}
        </div>
        <h4>{view === 'gcov' ? 'Observation snapshot' : 'Observation pair'}</h4>
        {shown.map((g) => <GroupOption key={g.id} g={g} selected={g.id === group.id} onSelect={() => p.onGroup(g.id)} />)}
        <h4>Measurement</h4>
        {layers.length ? layers.map((l) => <LayerRow key={l.id} layer={l} active={l.id === p.activeId} onSelect={() => p.onLayer(l.id)} />)
          : <p className="muted">This observation has no {VIEWS.find((v) => v.id === view)?.label} product.</p>}
      </section>}

      <section>
        <h3 className="label">Display</h3>
        {terrain && <LayerRow layer={terrain} active={terrain.id === p.activeId} onSelect={() => p.onLayer(terrain.id)} />}
        <label className="check switch"><input type="checkbox" checked={p.showTerrain} onChange={(e) => p.onTerrain(e.target.checked)} />Terrain background</label>
        {active && active.id !== terrain?.id && <label className="check"><input type="checkbox" checked={p.layerVisible} onChange={(e) => p.onLayerVisible(e.target.checked)} />Show {active.name}</label>}
        {active && active.id !== terrain?.id && (
          <label className="slider">Layer opacity <span>{Math.round(p.opacity * 100)}%</span>
            <input type="range" min={0} max={1} step={0.05} value={p.opacity} onChange={(e) => p.onOpacity(Number(e.target.value))} />
          </label>
        )}
        {steps && steps.length > 1 && (
          <label className="slider">Time of day <span>{steps[Math.min(p.step, steps.length - 1)].label}</span>
            <input type="range" aria-label="Time of day" min={0} max={steps.length - 1} step={1} value={p.step} onChange={(e) => p.onStep(Number(e.target.value))} />
          </label>
        )}
        {canMask && <label className="check"><input type="checkbox" checked={p.showMask} onChange={(e) => p.onMask(e.target.checked)} />Show masked pixels</label>}
        {overlays.length > 0 && (
          <label className="select">Quality overlay
            <select value={p.overlayId} onChange={(e) => p.onOverlay(e.target.value)}>
              <option value="">None</option>
              {overlays.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </label>
        )}
      </section>

      {refs.length > 0 && <section>
        <details className="refs" open>
        <summary><span className="label">Reference layers</span><span className="count">{p.referenceIds.filter((id) => refs.some((r) => r.id === id)).length} of {refs.length} on</span></summary>
        <p className="muted small">Independent sources, not NISAR measurements. Each keeps its own source and limits.</p>
        {missions.map((mission) => (
          <div key={mission}>
            <h4>{mission}</h4>
            {refs.filter((r) => r.mission === mission).map((r) => (
              <div className="ref-row" key={r.id}>
                <label className="check"><input type="checkbox" checked={p.referenceIds.includes(r.id)} onChange={(e) => p.onReference(r.id, e.target.checked)} />{r.name}</label>
                <button className="link" aria-label={`About ${r.name}`} onClick={() => p.onAbout(r.id)}>About</button>
              </div>
            ))}
          </div>
        ))}
        </details>
      </section>}
    </div>
  )
}
