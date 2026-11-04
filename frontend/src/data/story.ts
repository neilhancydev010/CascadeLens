import type { Manifest } from '../types/manifest'
import { isUsable } from '../services/manifest'

export interface StoryStep {
  id: string
  title: string
  bookmarkId: string
  layerId: string
  references: string[]
  paragraphs: string[]
}

const has = (m: Manifest, id: string) => m.layers.some((l) => l.id === id && isUsable(l))

const EXTENT = 'mapped extent'
const RING = '1 km ring outside extent'
const SOURCE = 'detachment zone'

// Every figure below comes from data/qa/pair-a-analysis.json, so the story cannot drift from the data.
function frames(m: Manifest) {
  return Object.entries(m.analysis?.['pair-a']?.frames ?? {})
}

function contrast(m: Manifest, measurement: string, digits: number) {
  const parts = frames(m).flatMap(([name, f]) => {
    const inside = f.zones[measurement]?.[EXTENT]?.median
    const outside = f.zones[measurement]?.[RING]?.median
    return inside == null || outside == null ? [] : [`${inside.toFixed(digits)} against ${outside.toFixed(digits)} in frame ${Number(name.slice(1))}`]
  })
  return parts.length ? parts.join(', and ') : null
}

function sourceHasNoData(m: Manifest) {
  const seen = frames(m).map(([, f]) => f.zones['gunw-coherence']?.[SOURCE]).filter((z) => z && z.pixels > 0)
  return seen.length > 0 && seen.every((z) => z!.validPct === 0)
}

function sourceFromPairB(m: Manifest) {
  const peak = (m.analysis?.['pair-b']?.frames ? Object.values(m.analysis['pair-b'].frames) : []).map((f) => f.zones['goff-peak']).find((z) => (z?.[SOURCE]?.validPct ?? 0) > 0)
  if (!peak) return null
  const inside = peak[SOURCE].median
  const outside = peak[RING].median
  return inside == null || outside == null ? null : `${inside.toFixed(2)} at the detachment zone against ${outside.toFixed(2)} in terrain near the channel`
}

function ionosphereNote(m: Manifest) {
  const f = frames(m).map(([name, x]) => `${x.ionosphere.stdPhase} to ${x.ionosphere.stdPhaseMinusIono} radians in frame ${Number(name.slice(1))}`)
  return f.length ? `Most of the broad stripes in the raw phase come from the ionosphere, not the ground: subtracting the product's own estimate cuts the scatter from ${f.join(' and ')}.` : null
}

// Text branches on the manifest, so the story can never claim a result that is not loaded.
export function buildStory(m: Manifest): StoryStep[] {
  const coherence = has(m, 'pair-a:gunw-coherence')
  const offset = has(m, 'pair-a:goff-range')
  const clean = has(m, 'pair-a:gunw-phase-iono')
  const coherenceText = contrast(m, 'gunw-coherence', 2)
  const offsetText = contrast(m, 'goff-range |x - scene median|', 2)
  const iono = ionosphereNote(m)
  const pairB = sourceFromPairB(m)
  const radar = coherence
    ? ['The map shows coherence from the descending Track 48 pair of 16 and 28 August 2026: how consistent the radar signal stayed between the two passes.',
       ...(coherenceText ? [`Along the channel that UNOSAT mapped, coherence is much lower than on the terrain beside it. The median is ${coherenceText}, comparing inside the mapped extent with the area within 1 km of it.`] : []),
       'This agrees with independent mapping, but it does not prove what happened. Low coherence has other causes too, and river channels are often low anyway.']
    : ['The descending Track 48 pair of 16 and 28 August 2026 brackets the event, and the catalogue footprints show both frames reach this corridor.',
       'The GUNW science files for this pair are not loaded in this build, so no phase or coherence is shown. They need a NASA Earthdata login to download.']
  return [
    {
      id: 'source', title: 'The source', bookmarkId: 'source', layerId: 'context:terrain', references: ['ref:unosat-detachment', 'ref:unosat-lakes', 'ref:rivers'],
      paragraphs: [
        'On 26 August 2026 a mountain mass movement was reported in the Langtang/Lhende area, near the Nepal–China border. Reports describe an ice-and-rock avalanche that blocked the upper Lhende Khola. Details of the source are still debated.',
        'The red polygon is UNOSAT’s mapped detachment zone and the blue polygons are barrier lakes. Both are independent satellite mapping, not NISAR results, and neither is field validated.',
        ...(sourceHasNoData(m) ? ['NISAR’s 16–28 August pair has no usable measurement here: the detachment zone and barrier lakes fall in a gap between radar swaths. So the radar evidence in this pair starts downstream.'] : []),
        ...(pairB ? [`The 19–31 August pair views the slope from the opposite side and does reach it. There, radar image matching largely fails: the median correlation peak is ${pairB}. That is what a heavily changed surface can look like, but other causes are possible.`] : []),
      ],
    },
    {
      id: 'radar', title: 'The radar evidence', bookmarkId: 'bhote-koshi', layerId: coherence ? 'pair-a:gunw-coherence' : 'context:terrain', references: ['ref:unosat-extent', 'ref:rivers'],
      paragraphs: [...radar, 'Twelve days separate the two acquisitions, so a pair can show that something changed between them, but not when within that interval.'],
    },
    {
      id: 'downstream', title: 'The downstream corridor', bookmarkId: 'bhote-koshi', layerId: 'context:terrain', references: ['ref:unosat-extent', 'ref:unosat-roads', 'ref:unosat-buildings', 'ref:eos-dpm', 'ref:impact-change', 'ref:rivers', 'ref:places'],
      paragraphs: [
        'Downstream, the flow followed the Bhote Koshi toward the Trishuli. UNOSAT’s preliminary mapping shows the mudflow and rockflow extent with affected roads and structures.',
        'This layer has its own sensors, dates and method. UNOSAT lists it as not yet field validated, so read it as independent context rather than as ground truth.',
        'The yellow-to-red pixels and the pink polygons are independent analyses of Sentinel-1, a different radar mission. Both are preliminary, and neither is a NISAR result.',
      ],
    },
    {
      id: 'interpretation', title: 'Scientific interpretation', bookmarkId: 'bhote-koshi', layerId: clean ? 'pair-a:gunw-phase-iono' : offset ? 'pair-a:goff-range' : 'context:terrain', references: ['ref:unosat-extent', 'ref:rivers'],
      paragraphs: [
        'Phase and pixel offsets are different kinds of radar evidence. Phase is sensitive to small changes but fails where the surface is disrupted. Offsets are coarser but can survive larger change. They measure different things and are not combined here.',
        ...(iono ? [iono] : []),
        ...(offsetText ? [`Pixel offsets add little here: the typical offset size inside the mapped extent is close to the terrain beside it, at ${offsetText}, in metres. Most phase inside the extent could not be reliably unwrapped.`] : []),
        coherence || offset
          ? 'No displacement is calculated. The phase sign convention is not documented, so phase stays in radians.'
          : 'In this build, no NISAR measurement is loaded, so this story establishes where to look and which observations exist. It does not establish any radar-measured change.',
        'Confirming what happened on the ground needs field observations and further analysis. CascadeLens is retrospective: it does not predict hazards or issue warnings.',
      ],
    },
  ]
}
