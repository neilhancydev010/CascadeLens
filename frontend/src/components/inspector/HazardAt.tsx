import { useEffect, useState } from 'react'
import type { Manifest } from '../../types/manifest'
import { samplePoint } from '../../services/sampler'
import { nearestRoad, terrainClass, terrainFactors, terrainLayer, type RoadSegment } from '../../services/hazards'
import { roadEvidence } from '../../services/roadEvidence'
import { RoadEvidencePanel } from './RoadEvidencePanel'
import { AddCheckButton } from '../fieldchecks/FieldChecksPanel'

// Terrain screen and the nearest screened road, for the clicked spot. Both experimental, and labelled so.
export function HazardAt({ manifest, point, onOpenCheck }: { manifest: Manifest; point: [number, number]; onOpenCheck?: (id: string) => void }) {
  const layer = terrainLayer(manifest)
  const [flags, setFlags] = useState<number | null | undefined>(undefined)
  const [road, setRoad] = useState<RoadSegment | null | undefined>(undefined)
  useEffect(() => {
    let stale = false
    setFlags(undefined); setRoad(undefined)
    if (layer) samplePoint(layer, point[0], point[1]).then((r) => { if (!stale) setFlags(r.state === 'valid' && r.value !== undefined ? r.value : null) })
    nearestRoad(manifest, point).then((s) => { if (!stale) setRoad(s) })
    return () => { stale = true }
  }, [layer, manifest, point])
  if (!layer && !manifest.hazards) return null
  const cls = flags != null ? manifest.hazards?.terrain.classes.find((c) => c.code === terrainClass(flags)) : undefined
  return (
    <section className="hazard-at" aria-label="Hazard screens here">
      <h3>Hazard screens here <span className="exp">Experimental</span></h3>
      {layer && (flags === undefined ? <p className="muted small">Checking the terrain…</p> : flags === null ? <p className="muted small">No terrain screen at this spot.</p> : (
        <div className="hz-row">
          <span>Landslide-prone terrain</span>
          <b style={{ color: cls?.color }}><i style={{ background: cls?.color }} />{cls?.label}</b>
          <ul>{terrainFactors(flags).map((t) => <li key={t}>{t}</li>)}</ul>
        </div>
      ))}
      {road && (
        <div className="hz-row">
          <span>Road within {road.distanceM} m ({road.road})</span>
          <b style={{ color: road.color }}><i style={{ background: road.color }} />{road.exposure} exposure</b>
          <ul>
            {road.reasons.length ? road.reasons.map((r) => <li key={r}>{r}</li>) : <li>No exposure factor found along this stretch.</li>}
            <li>{road.radarWatch}: the event pair could see a change on {road.radarUsablePct}% of this stretch{road.radarUnseenPct >= 50 ? ', and most of it lies beyond the frame checked' : road.radarHiddenPct >= 20 ? `, ${road.radarHiddenPct}% is hidden by terrain` : ''}.</li>
          </ul>
          <RoadEvidencePanel ev={roadEvidence(manifest, road)} />
          <AddCheckButton manifest={manifest} road={road} onOpen={onOpenCheck} />
        </div>
      )}
      <p className="muted small">Screens of terrain and position only, not forecasts. They leave out geology, soil and rainfall.</p>
    </section>
  )
}
