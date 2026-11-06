import { Component, lazy, Suspense, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { Bookmark, Manifest } from '../types/manifest'
import { CASES, currentCase, isUsable, loadManifest, STATUS_LABEL } from '../services/manifest'
import { buildStory } from '../data/story'
import { LeftPanel, type EvidenceView } from '../components/layout/LeftPanel'
import type { MapStatus } from '../components/map/MapView'
import { Legend } from '../components/legends/Legend'
import { Credits } from '../components/legends/Credits'
import { Inspector } from '../components/inspector/Inspector'
import { Interpretation } from '../components/explanations/Interpretation'
import { AboutSource } from '../components/explanations/AboutSource'
import { StoryPanel } from '../components/story/StoryPanel'
import { SimPanel } from '../components/sim/SimPanel'
import { ComparePanel } from '../components/compare/ComparePanel'
import { ScenarioPanel } from '../components/scenario/ScenarioPanel'
import { useAutoHidePanels } from './useAutoHidePanels'
import type { SimData, SimView } from '../services/simulation'

const TERRAIN = 'context:terrain'
const HILLSHADE = 'context:hillshade'
const SCENARIO_REFS = ['ref:lake-edge', 'ref:scenario-route', 'ref:scenario-extent']
const SIM_REFERENCES = ['ref:unosat-detachment', 'ref:unosat-lakes', 'ref:unosat-extent', 'ref:rivers', 'ref:places']
const NO_FOOTPRINTS: Manifest['granules'] = []

// The map library is most of the app's code. Starting its download here lets the panels appear without waiting for it.
const mapCode = import('../components/map/MapView')
const MapView = lazy(() => mapCode.then((m) => ({ default: m.MapView })))
// The 3D library is large and only lake cases use it, so it loads on first use.
const Terrain3D = lazy(() => import('../components/terrain/Terrain3D').then((m) => ({ default: m.Terrain3D })))

// WebGL can be unavailable or lost. The panels stay readable if the map cannot run.
class MapBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null }
  static getDerivedStateFromError(e: Error) { return { error: e.message } }
  render() {
    return this.state.error ? <p className="map-alert" role="alert">The map could not run: {this.state.error}</p> : this.props.children
  }
}

export function App() {
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    loadManifest().then((m) => { if (live) setManifest(m) }).catch((e: Error) => { if (live) setFailure(e.message) })
    return () => { live = false }
  }, [])
  if (failure) return <main className="splash"><h1>GAIA CascadeLens could not start</h1><p>{failure}</p><p>Run the processing scripts to generate the data manifest, then reload.</p></main>
  if (!manifest) return <main className="splash"><p>Initializing…</p></main>
  return <Explorer manifest={manifest} />
}

function Explorer({ manifest: m }: { manifest: Manifest }) {
  const primary = m.groups.find((g) => g.kind === 'pair')
  const firstLayer = m.layers.find((l) => (primary ? l.groupId === primary.id : l.category === 'gridded') && isUsable(l))
  const [groupId, setGroupId] = useState(primary?.id ?? '')
  const [step, setStep] = useState(0)
  const [view, setView] = useState<EvidenceView>('gunw')
  const [activeId, setActiveId] = useState(firstLayer?.id ?? TERRAIN)
  const [layerVisible, setLayerVisible] = useState(true)
  const [overlayId, setOverlayId] = useState('')
  const [showMask, setShowMask] = useState(false)
  const [showTerrain, setShowTerrain] = useState(true)
  const [opacity, setOpacity] = useState(0.85)
  const [referenceIds, setReferenceIds] = useState<string[]>(['ref:unosat-extent', 'ref:rivers', 'ref:places', 'ref:lake-edge'])
  const [bookmarkId, setBookmarkId] = useState<string | null>(null)
  const [focus, setFocus] = useState<{ bounds: Bookmark['bounds']; nonce: number } | null>(null)
  const [point, setPoint] = useState<[number, number] | null>(null)
  const [storyStep, setStoryStep] = useState<number | null>(null)
  const [simOn, setSimOn] = useState(false)
  const [compareOn, setCompareOn] = useState(false)
  const [threeOn, setThreeOn] = useState(false)
  const [scenarioOn, setScenarioOn] = useState(false)
  const [sim, setSim] = useState<SimView | null>(null)
  const [mapStatus, setMapStatus] = useState<MapStatus>({ state: 'loading' })
  const [covered, setCovered] = useState(true)
  const [panel, setPanel] = useState<'left' | 'right' | null>(null)
  const edges = useAutoHidePanels(`${storyStep}-${simOn}-${compareOn}-${threeOn}-${scenarioOn}`)
  const [tab, setTab] = useState<'inspect' | 'about'>('about')
  const [aboutId, setAboutId] = useState<string | null>(null)

  const byId = useCallback((id: string) => m.layers.find((l) => l.id === id), [m])
  const group = m.groups.find((g) => g.id === groupId)
  const active = useMemo(() => {
    const l = byId(activeId)
    return l?.timeSteps ? { ...l, sources: l.timeSteps[Math.min(step, l.timeSteps.length - 1)].sources } : l
  }, [byId, activeId, step])
  const terrain = byId(scenarioOn && byId(HILLSHADE) ? HILLSHADE : TERRAIN)
  const references = useMemo(() => referenceIds.map(byId).filter((l): l is NonNullable<typeof l> => Boolean(l && isUsable(l))), [referenceIds, byId])
  const overlay = overlayId ? byId(overlayId) : undefined
  const footprints = useMemo(() => {
    const seen = new Set<number>()
    return m.granules.filter((g) => g.group === groupId && !seen.has(g.frame) && Boolean(seen.add(g.frame)))
  }, [m, groupId])
  const story = useMemo(() => (m.groups.length || m.lake ? buildStory(m) : []), [m])
  const shownLayer = layerVisible ? active : undefined
  const detail = (aboutId && byId(aboutId)) || active
  const bookmark = m.bookmarks.find((b) => b.id === bookmarkId)
  const provisional = /provisional|preliminary/i.test(active?.productMaturity ?? '')

  const selectLayer = (id: string) => { setActiveId(id); setOverlayId(''); setShowMask(false); setLayerVisible(true); setAboutId(null) }

  const goToBookmark = useCallback((b: Bookmark) => {
    setBookmarkId(b.id)
    setFocus({ bounds: b.bounds, nonce: Date.now() })
    if (b.anchor) setPoint([b.anchor.lng, b.anchor.lat])
  }, [])

  const selectGroup = (id: string) => {
    setGroupId(id)
    const same = byId(`${id}:${active?.measurementType}`)
    const next = same && isUsable(same) ? same : m.layers.find((l) => l.groupId === id && isUsable(l))
    selectLayer(next?.id ?? TERRAIN)
  }

  // Same point, same bookmark, different technique: that is the dual-evidence comparison.
  const selectView = (v: EvidenceView) => {
    setView(v)
    if (!group) return
    const target = (v === 'gcov') !== (group.kind === 'snapshot') ? m.groups.find((g) => g.kind === (v === 'gcov' ? 'snapshot' : 'pair'))! : group
    setGroupId(target.id)
    const next = m.layers.find((l) => l.groupId === target.id && (l.category === v || l.previewOf === v) && isUsable(l))
    selectLayer(next?.id ?? TERRAIN)
  }

  const exitSim = () => { setSimOn(false); setSim(null) }

  const startCompare = () => { setStoryStep(null); exitSim(); setPanel(null); setThreeOn(false); setScenarioOn(false); setCompareOn(true) }
  const start3d = () => { setStoryStep(null); exitSim(); setPanel(null); setCompareOn(false); setScenarioOn(false); setThreeOn(true) }
  const scenarioBounds = (): Bookmark['bounds'] | null => {
    const pts = m.lake?.scenario?.marks.filter((q) => q.km <= 45).map((q) => q.lngLat) ?? [] // the first 45 km, where timing matters most
    if (!pts.length) return null
    const xs = pts.map((q) => q[0]), ys = pts.map((q) => q[1])
    return [Math.min(...xs) - 0.02, Math.min(...ys) - 0.02, Math.max(...xs) + 0.02, Math.max(...ys) + 0.02]
  }
  const startScenario = () => {
    setStoryStep(null); exitSim(); setPanel(null); setCompareOn(false); setThreeOn(false); setScenarioOn(true)
    selectLayer(HILLSHADE)
    setReferenceIds(SCENARIO_REFS)
    setBookmarkId(null)
    const b = scenarioBounds()
    if (b) setFocus({ bounds: b, nonce: Date.now() })
  }

  const startSim = () => {
    setStoryStep(null)
    setPanel(null)
    setCompareOn(false)
    setThreeOn(false)
    if (caseSimulation) {
      selectLayer(TERRAIN)
      setReferenceIds(SIM_REFERENCES)
      setBookmarkId(null)
    }
    setSimOn(true)
  }

  const frameSim = (d: SimData) => {
    const lngs = d.path.map((p) => p[0])
    const lats = d.path.map((p) => p[1])
    setFocus({ bounds: [Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)], nonce: Date.now() })
  }

  const goExplore = () => { setStoryStep(null); exitSim(); setCompareOn(false); setThreeOn(false); setScenarioOn(false) }

  const goStory = (i: number) => {
    const s = story[i]
    exitSim()
    setCompareOn(false)
    setThreeOn(false)
    setScenarioOn(s.id === 'scenario')
    setStoryStep(i)
    setPanel(null)
    selectLayer(s.layerId)
    setReferenceIds(s.references)
    const b = m.bookmarks.find((x) => x.id === s.bookmarkId)
    const sb = s.id === 'scenario' ? scenarioBounds() : null
    if (sb) { setBookmarkId(null); setFocus({ bounds: sb, nonce: Date.now() }) } else if (b) goToBookmark(b)
  }

  // A lake case opens on its guided story: risk, data, verdict, then what's next
  useEffect(() => { if (m.lake && story.length) goStory(0) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const caseSimulation = currentCase().simulation
  const timeLayer = m.layers.find((l) => (l.timeSteps?.length ?? 0) > 1 && isUsable(l))
  const canSimulate = Boolean(caseSimulation)
  const showTimeLayer = () => { if (!active?.timeSteps && timeLayer) selectLayer(timeLayer.id) }

  const showAbout = (id: string) => { setAboutId(id); setTab('about'); setPanel('right') }

  return (
    <div className={`app ${panel ? `show-${panel}` : ''} ${storyStep !== null ? 'story-on' : ''} ${simOn ? 'sim-on' : ''} ${compareOn ? 'compare-on' : ''} ${threeOn ? 'three-on' : ''} ${edges.hideLeft ? 'hide-left' : ''} ${edges.hideRight ? 'hide-right' : ''}`}>
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden="true"><svg viewBox="0 0 24 24" width="18" height="18"><circle cx="10.5" cy="10.5" r="6" fill="none" stroke="#fff" strokeWidth="2.2" /><path d="M15 15l5 5" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" /></svg></span>
          <span className="brand-text"><strong>CascadeLens</strong><span>by Team GAIA</span></span>
        </div>
        {CASES.length > 1 ? (
          <label className="case-pill"><i aria-hidden="true" /><span className="sr-only">Case study</span>
            <select value={currentCase().id} onChange={(e) => { window.location.search = `?case=${e.target.value}` }}>
              {CASES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
          </label>
        ) : <p className="case-pill single"><i aria-hidden="true" /><span>{currentCase().label}</span></p>}
        {(story.length > 0 || canSimulate || m.lake) && (
          <div className="modes" role="group" aria-label="Mode">
            {story.length > 0 && <button className={storyStep !== null ? 'on' : ''} aria-pressed={storyStep !== null} onClick={() => storyStep === null && goStory(0)}>Guided story</button>}
            <button className={storyStep === null && !simOn && !compareOn && !threeOn && !scenarioOn ? 'on' : ''} aria-pressed={storyStep === null && !simOn && !compareOn && !threeOn && !scenarioOn} onClick={goExplore}>Explore</button>
            {m.lake && <button className={compareOn ? 'on' : ''} aria-pressed={compareOn} onClick={() => !compareOn && startCompare()}>Compare</button>}
            {m.lake?.terrain && <button className={threeOn ? 'on' : ''} aria-pressed={threeOn} onClick={() => !threeOn && start3d()}>3D</button>}
            {m.lake?.scenario && <button className={scenarioOn && storyStep === null ? 'on' : ''} aria-pressed={scenarioOn && storyStep === null} onClick={() => !(scenarioOn && storyStep === null) && startScenario()}>What if</button>}
            {canSimulate && <button className={simOn ? 'on' : ''} aria-pressed={simOn} onClick={() => !simOn && startSim()}>Simulate</button>}
          </div>
        )}
        <div className="top-actions">
          {provisional && <span className="badge amber" title={active?.productMaturity}>Provisional data</span>}
          <button className="mobile-only" aria-expanded={panel === 'left'} onClick={() => setPanel(panel === 'left' ? null : 'left')}>Layers</button>
          <button className="mobile-only" aria-expanded={panel === 'right'} onClick={() => setPanel(panel === 'right' ? null : 'right')}>Details</button>
          <span className={`badge map-state map-${mapStatus.state}`} role="status">{mapStatus.state === 'error' ? 'Map source failed' : mapStatus.state === 'loading' ? 'Loading map data' : 'Map ready'}</span>
        </div>
      </header>
      {m.fixture && <p className="fixture-banner">{m.fixtureLabel ?? 'SYNTHETIC TEST FIXTURE. These values are invented for software testing and are not satellite data.'}</p>}

      <aside className="left" aria-label="Controls">
        <div className="sheet-handle" aria-hidden="true" />
        <LeftPanel manifest={m} group={group} view={view} activeId={activeId} step={step} onStep={setStep} hasStory={story.length > 0} storySteps={story.length} layerVisible={layerVisible} bookmarkId={bookmarkId} opacity={opacity} showTerrain={showTerrain} showMask={showMask} overlayId={overlayId}
          referenceIds={referenceIds} storyActive={storyStep !== null} simActive={simOn} canSimulate={canSimulate} onSimulate={startSim} canCompare={Boolean(m.lake)} compareActive={compareOn} onCompare={startCompare} can3d={Boolean(m.lake?.terrain)} on3d={start3d} onBookmark={goToBookmark} onGroup={selectGroup} onView={selectView} onLayer={selectLayer} onLayerVisible={setLayerVisible} onOpacity={setOpacity} onTerrain={setShowTerrain}
          onMask={setShowMask} onOverlay={setOverlayId} onReference={(id, on) => setReferenceIds((r) => (on ? [...r, id] : r.filter((x) => x !== id)))} onAbout={showAbout} onStory={() => goStory(0)} />
      </aside>

      <main className="center">
        <MapBoundary>
          <Suspense fallback={null}>
            <MapView envelope={m.caseStudy.searchEnvelope} terrain={terrain} showTerrain={showTerrain} active={shownLayer} overlay={overlay} showMask={showMask} opacity={opacity} references={references}
              footprints={simOn ? NO_FOOTPRINTS : footprints} point={point} focus={focus} sim={sim} onPoint={(p) => { setPoint(p); setTab('inspect'); setAboutId(null); edges.showRight() }} onStatus={setMapStatus} onCoverage={setCovered} />
          </Suspense>
        </MapBoundary>
        {threeOn && m.lake?.terrain && (
          <Suspense fallback={<p className="terrain-status">Loading the 3D viewer…</p>}>
            <Terrain3D lake={m.lake} onExit={() => setThreeOn(false)} />
          </Suspense>
        )}
        {bookmark && <p className="place-chip">{bookmark.name}</p>}
        {mapStatus.state === 'error' && <p className="map-alert" role="alert">{mapStatus.message}</p>}
        {!covered && <p className="map-notice" role="status">No geographic coverage: {active?.name} has no data in this view.</p>}
        <Legend layer={shownLayer} references={references} />
        <div className="map-foot">
          <Credits layers={[terrain, shownLayer, ...references]} />
          <p className="signature">Made by <strong>Team GAIA</strong></p>
        </div>
      </main>

      {edges.hideLeft && <button className="edge-tab edge-left" onClick={edges.showLeft} aria-label="Show the controls panel"><span aria-hidden="true">›</span></button>}
      {edges.hideRight && storyStep === null && <button className="edge-tab edge-right" onClick={edges.showRight} aria-label="Show the details panel"><span aria-hidden="true">‹</span></button>}

      {storyStep !== null && (
        <div className="story-dock">
          <StoryPanel steps={story} index={storyStep} manifest={m} onGo={goStory} onExit={() => { setStoryStep(null); setScenarioOn(false) }} />
        </div>
      )}

      {simOn && (
        <div className="sim-dock">
          <SimPanel manifest={m} simulation={caseSimulation} layer={active} step={step} canTime={Boolean(timeLayer)} onStep={setStep} onTimeTab={showTimeLayer} onView={setSim} onLoaded={frameSim} onExit={exitSim} />
        </div>
      )}

      {scenarioOn && storyStep === null && m.lake?.scenario && (
        <div className="compare-dock">
          <ScenarioPanel lake={m.lake} onExit={goExplore} />
        </div>
      )}

      {compareOn && m.lake && (
        <div className="compare-dock">
          <ComparePanel lake={m.lake} onExit={() => setCompareOn(false)} />
        </div>
      )}

      {storyStep === null && !simOn && !compareOn && !threeOn && !scenarioOn && (
        <aside className="right" aria-label="Scientific interpretation">
          <div className="sheet-handle" aria-hidden="true" />
          {aboutId && detail && detail.category === 'reference' ? (
            <div className="panel-body"><AboutSource layer={detail} backLabel={active?.name ?? 'the map'} onBack={() => setAboutId(null)} /></div>
          ) : <div className="panel-body">
            <div className="badges">
              <span className="badge teal">{detail?.mission} {detail?.productType}</span>
              {detail && <span className={`badge status-${detail.status}`}>{STATUS_LABEL[detail.status]}</span>}
            </div>
            <h2 className="title">{detail?.name}</h2>
            {detail && <p className="subtitle">{detail.measurementClass}</p>}
            {aboutId ? <button className="link" onClick={() => setAboutId(null)}>Back to {active?.name}</button> : (
              <div className="tabs underline" role="tablist">
                <button role="tab" aria-selected={tab === 'about'} className={tab === 'about' ? 'on' : ''} onClick={() => setTab('about')}>Interpretation</button>
                <button role="tab" aria-selected={tab === 'inspect'} className={tab === 'inspect' ? 'on' : ''} onClick={() => setTab('inspect')}>Inspector</button>
              </div>
            )}
            {tab === 'inspect' && !aboutId ? <Inspector layer={active} layers={m.layers} point={point} bookmarks={m.bookmarks} /> : detail && <Interpretation layer={detail} layers={m.layers} />}
          </div>}
        </aside>
      )}
    </div>
  )
}
