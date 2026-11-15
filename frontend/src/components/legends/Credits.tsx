import type { Layer } from '../../types/manifest'

// Always visible, because the map can mix sources from different missions and every one has attribution terms.
export function Credits({ layers }: { layers: (Layer | undefined)[] }) {
  const unique = [...new Map(layers.filter((l): l is Layer => Boolean(l)).map((l) => [l.attribution, l])).values()]
  const missions = [...new Set(unique.map((l) => l.mission))]
  return (
    <details className="credits">
      <summary>Sources: {missions.join(' · ')}</summary>
      <ul>{unique.map((l) => <li key={l.attribution}>{l.attribution}</li>)}</ul>
    </details>
  )
}
