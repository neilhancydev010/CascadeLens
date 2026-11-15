import type { Manifest } from '../types/manifest'
import { framesChecked, observabilityCurrent } from './observability'
import type { RoadSegment } from './hazards'

// The evidence behind one screened road stretch (audit P0.3). The inspector panel and every report format are built from
// this one record, so what a reviewer reads on screen and what they export cannot disagree.

export interface RoadEvidence {
  id: string | null
  osmWay: string | null
  name: string | null
  road: string
  bridge: boolean
  lengthM: number
  distanceM: number
  exposure: string
  reasons: string[]
  radar: {
    pair: string | null
    baseline: string | null
    trackFrame: string | null
    granule: string | null
    baselineGranule: string | null
    methodVersion: number
    current: boolean
    watch: string
    shares: { label: string; pct: number | null }[]
    // the opposite viewing direction, judged on its own flags; never merged into the shares above
    otherView: { label: string; pair: string | null; usablePct: number; eitherPct: number; watch: string } | null
  }
  context: string[]
  verify: string[]
}

const day = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
const span = (p?: [string, string] | null) => (p ? `${day(p[0])} to ${day(p[1])}` : null)

// What the radar coverage of a stretch means for checking it. With a second viewing direction, the share usable from either
// direction decides whether radar can say anything; each direction still reports its own share.
function watchAdvice(usable: number, other: RoadEvidence['radar']['otherView']): string[] {
  const best = other ? other.eitherPct : usable
  if (other && usable < 50 && best >= 50)
    return [`This pair watched ${usable < 20 ? 'little' : 'only part'} of this stretch, but with the opposite side (${other.label}) ${best}% can be watched from at least one direction. Read that view before relying on either.`]
  if (best < 20)
    return [`${other ? 'Neither viewing direction could' : 'The event pair could not'} watch most of this stretch, so radar can neither confirm nor rule out a change here. Use optical images or field reports.`]
  if (best < 50) return [`${other ? 'The two viewing directions together' : 'The event pair'} watched only part of this stretch. Check the rest by other means.`]
  return []
}

export function roadEvidence(m: Manifest, s: RoadSegment): RoadEvidence {
  const o = m.observability
  const current = observabilityCurrent(m)
  const usable = s.radarUsablePct
  const outside = s.radarOutsidePct ?? null
  const shares = [
    { label: 'Usable for spotting change', pct: usable },
    { label: 'Seen, but not reliable', pct: s.radarUnreliablePct ?? null },
    { label: 'Hidden by terrain', pct: s.radarHiddenPct },
    { label: 'No valid data in the product', pct: s.radarNoValidPct ?? null },
    { label: 'Outside the frame checked', pct: outside },
    { label: 'Not assessed', pct: s.radarNotAssessedPct ?? null },
  ]
  const ov = s.radarOtherView ? m.observabilityViews?.[s.radarOtherView] : undefined
  const otherView = ov && s.radarOtherUsablePct != null && s.radarEitherUsablePct != null
    ? { label: ov.label, pair: span(ov.pair), usablePct: s.radarOtherUsablePct, eitherPct: s.radarEitherUsablePct, watch: s.radarWatchEither ?? '' }
    : null
  const steep = s.steepSharePct
  const context = [
    steep === null || steep === undefined ? 'Terrain not assessed: no valid elevation along this stretch.' : `${steep}% of the ground within 150 m screens High or Very high for slope failure.`,
    s.nearRiver ? 'Within 100 m of a mapped river (OpenStreetMap).' : 'More than 100 m from a mapped river.',
    s.mapped2026 ? 'Crosses ground UNOSAT mapped as hit by the 2026 mudflow, or a road UNOSAT mapped as affected.' : 'Not on ground UNOSAT mapped as hit in 2026.',
    ...(s.bridge ? [`A bridge in OpenStreetMap (bridge=${s.bridge}).`] : []),
    ...(s.osmStatus === 'Destroyed' ? ['OpenStreetMap maps this road as destroyed after the event (HOT export).'] : []),
  ]
  const verify = [
    ...(s.mapped2026 ? ['Compare with UNOSAT’s affected-road record and any field report for this stretch. UNOSAT’s mapping is not field validated.'] : []),
    ...(steep !== null && steep !== undefined && steep >= 10 ? ['Look for fresh scarps, debris or failed cut slopes within 150 m on an optical image taken after 26 Aug 2026, such as Sentinel-2.'] : []),
    ...(steep === null || steep === undefined ? ['Check the elevation model here: the terrain screen could not be computed.'] : []),
    ...(s.nearRiver ? ['Check the river bank and the road edge on recent imagery for erosion or new deposits.'] : []),
    ...(s.bridge ? ['Confirm the bridge is standing and passable, with the road authority or a field report.'] : []),
    ...(s.osmStatus === 'Destroyed' ? ['Check with the road authority whether this stretch has been reopened or bypassed since it was mapped as destroyed.'] : []),
    ...watchAdvice(usable, otherView),
    ...(outside !== null && outside >= 50 ? ['Most of this stretch lies beyond the radar frames checked, so this pair says nothing about it.'] : []),
    ...(!current ? ['These radar figures come from the withdrawn first observability method. Recheck them after the rebuild.'] : []),
    ...(s.exposure === 'Low' ? ['Low means no factor was found among those screened. It does not mean the road is safe.'] : []),
  ]
  return {
    id: s.id ?? null,
    osmWay: s.osmId ?? null,
    name: s.name ?? null,
    road: s.road,
    bridge: Boolean(s.bridge),
    lengthM: s.lengthM,
    distanceM: s.distanceM,
    exposure: s.exposure,
    reasons: s.reasons,
    radar: {
      pair: span(o?.pair),
      baseline: span(o?.baselinePair),
      trackFrame: o ? `Track ${o.track} ${String(o.orbit ?? '').toLowerCase()}, ${framesChecked(m).length > 1 ? `frames ${framesChecked(m).join(' and ')}` : `frame ${o.frame}`}`.replace('  ', ' ') : null,
      granule: o?.granule ?? null,
      baselineGranule: o?.baselineGranule ?? null,
      methodVersion: o?.methodVersion ?? 1,
      current,
      watch: s.radarWatch,
      shares,
      otherView,
    },
    context,
    verify,
  }
}
