import type { CSSProperties } from 'react'
import type { Layer } from '../../types/manifest'
import { STATUS_LABEL } from '../../services/manifest'
import { explanationFor } from '../../data/explanations'

// Each independent source gets its own badge so the panel reads as "who made this", not just "what layer".
export const MISSION_STYLE: Record<string, { short: string; color: string; about: string }> = {
  UNOSAT: { short: 'UN', color: '#6aa8ff', about: 'UN Satellite Centre (UNITAR)' },
  'Sentinel-1': { short: 'S1', color: '#ff7f66', about: 'Copernicus Sentinel-1 radar, analysed by partners' },
  OpenStreetMap: { short: 'OSM', color: '#7fd98c', about: 'Community-mapped geography' },
  'COD-AB': { short: 'COD', color: '#b9a4ff', about: 'Official administrative boundaries' },
}
export const missionStyle = (m: string) => MISSION_STYLE[m] ?? { short: m.slice(0, 3).toUpperCase(), color: '#5fe0c9', about: m }

// "UNOSAT barrier lakes (0.31 km²)" -> title "Barrier lakes", figure "0.31 km²".
export function splitName(l: Pick<Layer, 'name' | 'mission'>) {
  const figure = l.name.match(/\(([^)]*\d[^)]*)\)\s*$/)?.[1] ?? null
  let title = l.name.replace(/\s*\([^)]*\)\s*$/, '')
  if (figure === null && /\(([^)]*)\)\s*$/.test(l.name)) title = l.name
  title = title.replace(new RegExp(`^${l.mission}\\s+`), '')
  return { title: title.charAt(0).toUpperCase() + title.slice(1), figure }
}

const licence = (a: string) => a.match(/CC BY(?:-[A-Z]+)*|ODbL/)?.[0] ?? null

const Icon = ({ d }: { d: string }) => <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
const EYE = 'M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8zM8 10a2 2 0 100-4 2 2 0 000 4z'
const TARGET = 'M8 14.5A6.5 6.5 0 108 1.5a6.5 6.5 0 000 13zM8 11a3 3 0 100-6 3 3 0 000 6z'
const CHECK = 'M3 8.5l3 3 7-7'

export function AboutSource({ layer, backLabel, onBack }: { layer: Layer; backLabel: string; onBack: () => void }) {
  const e = explanationFor(layer)
  const s = missionStyle(layer.mission)
  const { title, figure } = splitName(layer)
  const lic = licence(layer.attribution)
  const provider = layer.attribution.split(',')[0]
  return (
    <div className="about">
      <button className="back-pill" onClick={onBack}><span aria-hidden="true">←</span> Back to {backLabel}</button>
      <header className="about-hero" style={{ '--mission': s.color } as CSSProperties}>
        <div className="about-hero-top">
          <span className="avatar" aria-hidden="true">{s.short}</span>
          <span className="about-who"><strong>{layer.mission}</strong><small>{s.about}</small></span>
          {layer.vector?.color && <span className="map-key" title="Colour on the map" style={{ background: layer.vector.color }} />}
        </div>
        <p className="eyebrow">Independent source · not NISAR</p>
        <h2 className="title">{title}</h2>
        {figure && <p className="hero-figure">{figure}</p>}
        <div className="chips-row">
          <span className="chip">{layer.acquisition.reference}</span>
          <span className="chip">{layer.measurementClass}</span>
          <span className={`chip status-${layer.status}`}>{STATUS_LABEL[layer.status]}</span>
          {lic && <span className="chip">{lic}</span>}
        </div>
      </header>

      <section className="about-summary">
        <p className="lead">{e.what}</p>
        <ul className="about-points">
          <li><span className="pt-icon"><Icon d={EYE} /></span><span><strong>What it shows</strong>{e.measures}</span></li>
          <li><span className="pt-icon"><Icon d={TARGET} /></span><span><strong>How to use it</strong>{e.inspect}</span></li>
          <li><span className="pt-icon"><Icon d={CHECK} /></span><span><strong>What it tells us</strong>{e.establishes}</span></li>
        </ul>
      </section>

      {layer.statusReason && <p className="notice">{layer.statusReason}</p>}

      <section className="callout">
        <h3 className="label">Limits</h3>
        <ul className="limits">{layer.limitations.map((t) => <li key={t}>{t}</li>)}</ul>
      </section>

      <footer className="about-source">
        <h3 className="label">Source</h3>
        <p><strong>{provider}</strong></p>
        <p className="attribution">{layer.attribution}</p>
        <p className="attribution">Maturity: {layer.productMaturity}</p>
        {layer.page && <a className="source-link" href={layer.page} target="_blank" rel="noreferrer">Open the original dataset ↗</a>}
      </footer>
    </div>
  )
}
