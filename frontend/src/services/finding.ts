import type { ControlPair, Manifest } from '../types/manifest'
import { beyondFrames, observabilityCurrent, STALE_NOTE } from './observability'

export interface Finding { headline: string; points: { label: string; text: string }[]; source: string }

const pct = (v: number | undefined) => (v === undefined ? '?' : `${Math.round(v)}%`)
const date = (d: string) => new Date(`${d}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })

// The bandwidth field of a GUNW file name (for example 2000 or 4000). Older series did not store it, but the granule name has it.
export const pairMode = (p: ControlPair) => p.mode ?? /_GUNW_\d{3}_\d{3}_[AD]_\d{3}_\d{3}_(\d{4})_/.exec(p.granule)?.[1] ?? null

// Why the before and across pairs are not like for like: a longer pair, or a different acquisition mode, changes coherence by itself.
export function comparability(pre: ControlPair, co: ControlPair): string {
  const parts = [`the pre-event pair spans ${pre.days} days and the event pair ${co.days}`]
  const a = pairMode(pre), b = pairMode(co)
  if (a && b && a !== b) parts.push(`they were acquired in different radar modes (${a} and ${b} in the file names)`)
  if (!a || !b) parts.push('their acquisition modes are not recorded here')
  return pre.days === co.days && parts.length === 1 ? '' : `The comparison is indicative: ${parts.join(', and ')}.`
}

// The first-minute card. Every figure is read from the manifest, so it changes with the data and never goes stale.
export function finding(m: Manifest): Finding | null {
  const cs = m.controlSeries, o = m.observability
  if (!cs || !o) return null
  const pre = cs.pairs.find((p) => p.pair[1] <= cs.eventDate)
  const co = cs.pairs.find((p) => p.pair[0] <= cs.eventDate && p.pair[1] >= cs.eventDate)
  const zone = (task: 'disturbance' | 'movement', id: string) => o.zones[task]?.[id]
  const det = 'vector:unosat_detachment_zone.geojson', flow = 'vector:unosat_mudflow_extent.geojson'
  const outside = zone('disturbance', flow)
  const points: Finding['points'] = []
  const dropped = Boolean(pre && co && co.inside < pre.inside && co.outside >= pre.outside)
  if (pre && co) {
    const legacy = (cs.methodVersion ?? 1) < 2 ? ' These medians come from an earlier script that is not in the repository; a reproducible run will replace them.' : ''
    points.push({ label: 'Measured change', text: `Inside the mapped mudflow, median radar coherence was ${pre.inside.toFixed(2)} in the pair before the event and ${co.inside.toFixed(2)} in the pair across it, while ground nearby went from ${pre.outside.toFixed(2)} to ${co.outside.toFixed(2)}. ${dropped ? 'That pattern is consistent with surface change in the mapped area. It does not establish the cause.' : 'This does not show a drop confined to the mapped area.'} ${comparability(pre, co)}${legacy}`.replace(/\s+/g, ' ').trim() })
  }
  if (observabilityCurrent(m)) {
    const d = zone('disturbance', det)?.percent, mv = zone('movement', det)?.percent
    if (d && mv) points.push({ label: 'What the radar could judge', text: `At the source, a surface change could be judged on ${pct(d.Usable)} of the ground, and ground movement could be measured on ${pct(mv.Usable)}. The rest has a reason attached: outside the frame, no valid data, hidden by terrain or not assessed.` })
  } else {
    points.push({ label: 'What the radar could judge', text: STALE_NOTE })
  }
  if (outside?.percent) points.push({ label: 'What it could not see', text: `${pct(outside.percent['Outside the frame checked'])} of the mapped mudflow lies ${beyondFrames(m)}. CascadeLens marks it as unchecked rather than letting it look unchanged.` })
  return {
    headline: dropped
      ? 'NISAR coherence fell inside the mapped Rasuwa mudflow across the event, and CascadeLens shows where the radar could and could not judge the ground.'
      : 'CascadeLens shows where NISAR could and could not judge the ground around the Rasuwa mudflow.',
    points,
    source: `NISAR GUNW, Track ${cs.track} ${cs.direction.toLowerCase()}, frame ${cs.frame}: ${co ? `${date(co.pair[0])} to ${date(co.pair[1])}` : ''}${pre ? `, control pair ${date(pre.pair[0])} to ${date(pre.pair[1])}` : ''}. Provisional products.`,
  }
}
