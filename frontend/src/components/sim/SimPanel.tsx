import { useEffect, useMemo, useState } from 'react'
import type { Layer, Manifest } from '../../types/manifest'
import { coherence, count, firstPass, loadSimulation, shift, SIM_CELLS, type SimData, type SimView } from '../../services/simulation'
import { Bars } from '../charts/Charts'
import { coherenceGroups } from '../story/StoryPanel'

interface Props {
  manifest: Manifest
  simulation?: string
  layer?: Layer
  step: number
  canTime: boolean
  onStep: (i: number) => void
  onTimeTab: () => void
  onView: (v: SimView | null) => void
  onLoaded: (d: SimData) => void
  onExit: () => void
}

type Tab = 'replay' | 'whatif' | 'time' | 'radar'

const TAB_LABELS: Record<Tab, string> = { replay: 'Flow replay', whatif: 'What-if flood', time: 'Time replay', radar: 'Radar explainer' }
const STEP_MS = 900
const REPLAY_SECONDS = 24
const n = (x: number) => Math.round(x).toLocaleString('en-GB')

function Profile({ data, km }: { data: SimData; km: number }) {
  const top = data.path[0][2]
  const last = data.path.length - 1
  const x = (i: number) => (i / last) * 300
  const y = (m: number) => 56 - (m / top) * 50
  return (
    <svg className="profile" viewBox="0 0 300 60" role="img" aria-label={`River level falling from ${n(top)} metres at the source to ${n(data.path[last][2])} metres at the end of the path`}>
      <polyline points={data.path.map((p, i) => `${x(i).toFixed(1)},${y(p[2]).toFixed(1)}`).join(' ')} />
      <circle cx={x(km)} cy={y(data.path[km][2])} r="4" />
    </svg>
  )
}

function Replay({ data, km, setKm }: { data: SimData; km: number; setKm: (k: number) => void }) {
  const [playing, setPlaying] = useState(false)
  const last = data.path.length - 1
  useEffect(() => {
    if (!playing) return
    let pos = km >= last ? 0 : km
    let before = performance.now()
    let frame = requestAnimationFrame(function tick(now) {
      pos += ((now - before) / 1000) * (last / REPLAY_SECONDS)
      before = now
      if (pos >= last) { setKm(last); setPlaying(false); return }
      setKm(Math.floor(pos)) // Whole kilometres, so the map redraws about 8 times a second, not 60
      frame = requestAnimationFrame(tick)
    })
    return () => cancelAnimationFrame(frame)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- km is only the starting point
  }, [playing, last])
  const seen = useMemo(() => count(data, km), [data, km])
  const next = data.places.find((p) => p.km > km)
  return (
    <>
      <p>The pulse follows the real river path from the mapped source. Orange shows what was mapped as affected along the stretch it has passed.</p>
      <div className="sim-controls">
        <button className="primary" onClick={() => setPlaying(!playing)}>{playing ? 'Pause' : km >= last ? 'Replay' : 'Play'}</button>
        <label className="slider grow">Distance from the source <span>{km} of {last} km</span>
          <input type="range" min={0} max={last} value={km} onChange={(e) => { setPlaying(false); setKm(Number(e.target.value)) }} />
        </label>
      </div>
      <Profile data={data} km={km} />
      <dl className="facts">
        <div><dt>River level here</dt><dd>{n(data.path[km][2])} m</dd></div>
        <div><dt>Next place</dt><dd>{next ? `${next.name}, km ${next.km}` : 'End of the path'}</dd></div>
        {data.totals.buildings > 0 && <div><dt>Buildings mapped as affected</dt><dd>{n(seen.buildings)} of {n(data.totals.buildings)}</dd></div>}
        {data.totals.mappedRoadKm > 0 && <div><dt>Roads mapped as affected</dt><dd>{n(seen.roadKm)} of {n(data.totals.mappedRoadKm)} km</dd></div>}
      </dl>
      <p className="notice small">Illustration only. The path is real, but the speed is not measured: nothing here shows when the flow reached any place.</p>
    </>
  )
}

function WhatIf({ data, reach, setReach, rise, setRise }: { data: SimData; reach: number; setReach: (k: number) => void; rise: number; setRise: (r: number) => void }) {
  const hit = useMemo(() => count(data, reach, rise), [data, reach, rise])
  const last = data.path.length - 1
  return (
    <>
      <p>Choose how high the water rises above the river and how far it travels. Orange shows what sits lower than that water.</p>
      <div className="sim-sliders">
        <label className="slider">Water rise above the river <span>{rise} m</span>
          <input type="range" min={5} max={80} value={rise} onChange={(e) => setRise(Number(e.target.value))} />
        </label>
        <label className="slider">How far it travels <span>{reach} km</span>
          <input type="range" min={10} max={last} value={reach} onChange={(e) => setReach(Number(e.target.value))} />
        </label>
      </div>
      <dl className="facts">
        {data.totals.buildings > 0 && <div><dt>Mapped buildings below the water</dt><dd>{n(hit.buildings)} of {n(data.totals.buildings)}</dd></div>}
        {data.totals.roadKm > 0 && <div><dt>Roads below the water</dt><dd>{n(hit.roadKm)} of {n(data.totals.roadKm)} km</dd></div>}
        <div className="wide"><dt>Places below the water: {hit.places.length} of {data.places.length}</dt><dd>{hit.places.join(', ') || 'None'}</dd></div>
      </dl>
      <p className="notice small">Rough what-if, not a forecast and never a safety guide. It compares ground height with the river and ignores water volume, speed and valley shape, and it has not been checked against real floods. Only buildings in the loaded data are counted, so others are missing.</p>
    </>
  )
}

function TimeReplay({ layer, step, onStep }: { layer?: Layer; step: number; onStep: (i: number) => void }) {
  const [playing, setPlaying] = useState(false)
  const steps = layer?.timeSteps
  const last = (steps?.length ?? 1) - 1
  const at = Math.min(step, last)
  useEffect(() => {
    if (!playing) return
    if (at >= last) { setPlaying(false); return }
    const timer = setTimeout(() => onStep(at + 1), STEP_MS)
    return () => clearTimeout(timer)
  }, [playing, at, last, onStep])
  if (!steps || last < 1) return <p className="notice">Choose a map layer that changes over time, in the panel on the left.</p>
  return (
    <>
      <p>This plays the stored data for {layer!.name} in order, one saved time after another. Choose another layer on the left to play that instead.</p>
      <div className="sim-controls">
        <button className="primary" onClick={() => { if (at >= last) onStep(0); setPlaying(!playing) }}>{playing ? 'Pause' : at >= last ? 'Replay' : 'Play'}</button>
        <label className="slider grow">Saved time <span>{steps[at].label}</span>
          <input type="range" min={0} max={last} value={at} onChange={(e) => { setPlaying(false); onStep(Number(e.target.value)) }} />
        </label>
      </div>
      <p className="notice small">Real stored values, with nothing filled in between the saved times. Nothing is predicted.</p>
    </>
  )
}

function Cells({ label, angle }: { label: string; angle: (i: number) => number }) {
  const side = Math.sqrt(SIM_CELLS)
  return (
    <figure>
      <svg viewBox={`0 0 ${side} ${side}`} aria-hidden="true">
        {Array.from({ length: SIM_CELLS }, (_, i) => <rect key={i} x={i % side} y={Math.floor(i / side)} width="1.02" height="1.02" fill={`hsl(${(angle(i) * 180) / Math.PI} 70% 55%)`} />)}
      </svg>
      <figcaption>{label}</figcaption>
    </figure>
  )
}

function Radar({ manifest }: { manifest: Manifest }) {
  const [change, setChange] = useState(20)
  const c = change / 100
  const value = coherence(c)
  return (
    <>
      <p>The satellite passes over the same ground twice. Each patch of ground returns its own colour of echo. If the ground stays put, the second pass shifts every patch alike, so the difference is one even colour. If the ground changes, the patches shift at random and the signal stops matching. That match is coherence.</p>
      <svg className="sat-track" viewBox="0 0 300 34" role="img" aria-label="A satellite crossing above the ground twice">
        <line x1="0" y1="31" x2="300" y2="31" />
        <g className="sat"><rect x="-5" y="4" width="10" height="7" rx="1.5" /><rect x="-15" y="6" width="8" height="3" /><rect x="7" y="6" width="8" height="3" /><path d="M0 11 L-9 30 L9 30 Z" /></g>
      </svg>
      <div className="sim-sliders">
        <label className="slider">How much the ground changed <span>{change}%</span>
          <input type="range" min={0} max={100} value={change} onChange={(e) => setChange(Number(e.target.value))} />
        </label>
      </div>
      <div className="story-body with-chart">
        <div className="cells">
          <Cells label="First pass" angle={firstPass} />
          <Cells label="Second pass" angle={(i) => firstPass(i) + shift(i, c)} />
          <Cells label="Difference" angle={(i) => shift(i, c)} />
        </div>
        <Bars title="Coherence: 0 = noisy, 1 = stable" groups={[{ label: 'This model', bars: [{ label: 'Simulated', value, color: 'var(--amber)' }] }, ...coherenceGroups(manifest)]} />
      </div>
      <p className="notice small">A teaching model with made-up ground, not the real radar processing. Low coherence has other causes too, such as water, snow and vegetation.</p>
    </>
  )
}

export function SimPanel({ manifest, simulation, layer, step, canTime, onStep, onTimeTab, onView, onLoaded, onExit }: Props) {
  const tabs: Tab[] = [...(simulation ? ['replay', 'whatif'] as const : []), ...(canTime ? ['time'] as const : []), ...(coherenceGroups(manifest).length ? ['radar'] as const : [])]
  const [tab, setTab] = useState<Tab>(tabs[0])
  const [data, setData] = useState<SimData | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [km, setKm] = useState(0)
  const [reach, setReach] = useState(0)
  const [rise, setRise] = useState(25)
  useEffect(() => {
    if (!simulation) return
    let live = true
    loadSimulation(simulation).then((d) => { if (!live) return; setData(d); setReach(d.path.length - 1); onLoaded(d) }).catch((e: Error) => { if (live) setFailure(e.message) })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once
  }, [])
  useEffect(() => {
    if (tab === 'time') onTimeTab()
    onView(data && (tab === 'replay' || tab === 'whatif') ? { data, mode: tab, km: tab === 'replay' ? km : reach, rise } : null)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onView is a state setter's wrapper
  }, [data, tab, km, reach, rise])
  return (
    <section className="story sim-panel" aria-label="Simulations">
      <div className="tabs segmented" role="tablist">
        {tabs.map((id) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'on' : ''} onClick={() => setTab(id)}>{TAB_LABELS[id]}</button>)}
      </div>
      {tab === 'radar' ? <Radar manifest={manifest} />
        : tab === 'time' ? <TimeReplay layer={layer} step={step} onStep={onStep} />
          : failure ? <p className="notice">The simulation could not start: {failure}</p>
          : !data ? <p className="muted">Loading the flow path…</p>
            : tab === 'replay' ? <Replay data={data} km={km} setKm={setKm} />
              : <WhatIf data={data} reach={reach} setReach={setReach} rise={rise} setRise={setRise} />}
      <footer><button className="ghost" onClick={onExit}>Exit simulation</button></footer>
    </section>
  )
}
