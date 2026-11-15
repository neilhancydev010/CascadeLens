import { useEffect } from 'react'
import { EvidenceTag } from './EvidenceTag'
import type { EvidenceClass } from '../../services/evidence'

// A short page for someone who has three minutes: the problem, the data, the method, the use and how it was built.
// Every source keeps its evidence class, and nothing here is stronger than the claims register (data/claims.json).

interface Source { name: string; by: string; use: string; kind: EvidenceClass; nasa?: boolean }

export const ABOUT_SOURCES: Source[] = [
  { name: 'NISAR GUNW and GOFF', by: 'NASA/JPL and ISRO, from the ASF DAAC through NASA Earthdata', use: 'Radar coherence, unwrapped phase and pixel offsets for pairs before and across the event. Provisional products (CRID P05023).', kind: 'observed', nasa: true },
  { name: 'NISAR GCOV', by: 'NASA/JPL and ISRO, from the ASF DAAC', use: 'Radar backscatter over Tsho Rolpa lake, and four Rasuwa snapshots: Track 48 on 16 and 28 August, Track 149 on 23 August and Track 98 on 12 September. Provisional (P05023).', kind: 'observed', nasa: true },
  { name: 'NISAR GCOV change, Track 48', by: 'Worked out by CascadeLens from two NISAR GCOV files', use: 'How the radar return changed between 16 and 28 August on the same track, across the event. Consistent with surface change; it does not establish the cause.', kind: 'derived', nasa: true },
  { name: 'OPERA RTC-S1', by: 'NASA/JPL OPERA, from Copernicus Sentinel-1 data, through the ASF DAAC', use: 'Terrain-corrected Sentinel-1 radar images. CascadeLens compares 12-day pairs before and across the event on two tracks. A different mission from NISAR.', kind: 'derived', nasa: true },
  { name: 'NASADEM', by: 'NASA JPL, from the LP DAAC', use: 'Terrain height and hillshade for the Rasuwa map and 3D model. From the February 2000 SRTM radar flight.', kind: 'reference', nasa: true },
  { name: 'GPM IMERG Late daily rainfall', by: 'NASA GES DISC, through NASA Earthdata', use: 'Rainfall history for a landslide rainfall-threshold test. The threshold did not beat chance, so no result relies on it.', kind: 'derived', nasa: true },
  { name: 'NASA Global Landslide Catalog', by: 'NASA Goddard Space Flight Center', use: 'Registered as a dated landslide inventory for Nepal. It ends in 2016 and no model is fitted to it.', kind: 'reference', nasa: true },
  { name: 'Copernicus DEM GLO-30', by: 'ESA / Copernicus', use: 'Terrain for Tsho Rolpa, and for the Rasuwa terrain screen, cliff-impact sites and What-if flood, which have not yet been rebuilt on NASADEM.', kind: 'reference' },
  { name: 'UNOSAT event mapping', by: 'UNOSAT / UNITAR', use: 'Mapped mudflow, barrier lakes, detachment zone and affected roads. Not yet field validated.', kind: 'reference' },
  { name: 'Sentinel-1 damage proxy and change screening', by: 'EOS-RS and IMPACT / REACH', use: 'Independent radar products from another mission, for comparison. Not NISAR results.', kind: 'reference' },
  { name: 'OpenStreetMap and HOT mapping', by: 'OpenStreetMap contributors', use: 'Rivers, roads, places, facilities and volunteer bridge reports.', kind: 'reference' },
  { name: 'BIPAD landslide incident reports', by: 'NDRRMA, Government of Nepal', use: 'Reports used only in the rainfall-threshold test. Licence not established, so the records are not shipped.', kind: 'reference' },
  { name: 'District boundaries (COD-AB)', by: 'Survey Department of Nepal and UN RCO, via OCHA', use: 'Context only.', kind: 'reference' },
]

export function AboutProject({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [onClose])
  return (
    <section className="status-panel about-project" role="dialog" aria-label="About CascadeLens and its NASA data">
      <header><h2>About CascadeLens</h2><button onClick={onClose} aria-label="Close" title="Close">×</button></header>
      <p className="muted small">Made by Team GAIA for the 2026 NASA Space Apps Challenge. It runs entirely in the browser from files published with the app: no server, no account and no download.</p>

      <h3>The problem</h3>
      <p className="small">On 26 August 2026 a mudflow and rockflow struck the Rasuwa–Bhote Koshi–Trishuli valley in Nepal. In steep mountain valleys one hazard can set off another: a slope fails, debris blocks a river, a lake forms behind it. After such an event, people need to know where the ground changed, and just as much, where the satellites could not see. Radar works through cloud and at night, but steep slopes can hide ground from it, and a place the radar did not see is not a safe place.</p>

      <h3>NASA and Earth observation data used</h3>
      <ul className="about-sources">
        {ABOUT_SOURCES.map((s) => (
          <li key={s.name}>
            <span className="about-source-head">{s.nasa && <span className="badge teal">NASA</span>}<strong>{s.name}</strong><EvidenceTag kind={s.kind} compact /></span>
            <small>{s.by}. {s.use}</small>
          </li>
        ))}
      </ul>
      <p className="muted small">Full details, licences and known issues are in docs/DATA_SOURCES.md in the repository.</p>

      <h3>How it works</h3>
      <ol className="about-steps small">
        <li><strong>Read.</strong> NISAR and OPERA files from NASA's ASF archive and NASADEM from NASA's LP DAAC are read directly, their values kept as measured, averaged to a 40 m grid and cut into map tiles.</li>
        <li><strong>Compare.</strong> Radar coherence before the event is compared with coherence across it, inside and outside the area UNOSAT mapped. CascadeLens also works out where the radar could judge the ground and gives a reason where it could not: outside the frame, no valid data, or hidden by terrain.</li>
        <li><strong>Show.</strong> Everything goes on one map with its evidence class, source and limits, so a reader can tell what was measured, what was calculated and what is only an illustration.</li>
      </ol>
      <p className="muted small">A drop in coherence is consistent with surface change. It does not establish the cause, and the products are provisional.</p>

      <h3>Real-world use</h3>
      <p className="small">After an event, CascadeLens helps analysts and responders decide where to look next: which places show measured change, which were never seen by the radar, and where a field check or another satellite pass would help most. It supports decisions with evidence. It is not a warning system and does not forecast. Simulate and What if are illustrations, marked as scenarios, not predictions.</p>

      <h3>AI and computing</h3>
      <p className="small">The team used Claude, an AI assistant made by Anthropic, to help write, review and test the code and documentation. The analysis itself does not use machine learning or AI: it is ordinary radar processing and statistics, such as coherence medians, pixel offsets and terrain geometry. One statistical rainfall threshold was fitted with a standard published method; it did not beat chance, and the app says so. The processing scripts are in Python in the repository, and the app is a static website.</p>
    </section>
  )
}
