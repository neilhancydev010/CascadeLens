import { useState } from 'react'
import type { Manifest } from '../../types/manifest'
import { buildReport, save, toCsv, toGeoJson, toHtml, type Report } from '../../services/report'

type Kind = 'pdf' | 'csv' | 'geojson' | 'json'

// Downloads one evidence report for the clicked spot. Everything is built in the browser from the data already shown.
export function ReportButtons({ manifest, point }: { manifest: Manifest; point: [number, number] }) {
  const [busy, setBusy] = useState(false)
  const base = `cascadelens-${manifest.caseStudy.id}-${point[1].toFixed(4)}N-${point[0].toFixed(4)}E`
  async function run(kind: Kind) {
    // The print window must open inside the click, before any await, or browsers block it.
    const win = kind === 'pdf' ? window.open('', '_blank') : null
    setBusy(true)
    try {
      const r: Report = await buildReport(manifest, point)
      if (kind === 'csv') save(`${base}.csv`, toCsv(r), 'text/csv')
      if (kind === 'geojson') save(`${base}.geojson`, toGeoJson(r), 'application/geo+json')
      if (kind === 'json') save(`${base}.json`, JSON.stringify(r, null, 1), 'application/json')
      if (kind === 'pdf') {
        if (win) {
          win.document.open(); win.document.write(toHtml(r)); win.document.close()
          // The new window inherits the offline policy, which blocks a script inside the page. A listener added from here is allowed.
          win.document.getElementById('print')?.addEventListener('click', () => win.print())
        } else save(`${base}.html`, toHtml(r, true), 'text/html')
      }
    } finally { setBusy(false) }
  }
  return (
    <section className="report-btns" aria-label="Evidence report">
      <h3>Evidence report for this spot</h3>
      <div className="chips">
        <button onClick={() => run('pdf')} disabled={busy}>Printable / PDF</button>
        <button onClick={() => run('csv')} disabled={busy}>CSV</button>
        <button onClick={() => run('geojson')} disabled={busy}>GeoJSON</button>
        <button onClick={() => run('json')} disabled={busy}>JSON</button>
      </div>
      {busy && <p className="muted small">Reading every layer at this spot…</p>}
    </section>
  )
}
