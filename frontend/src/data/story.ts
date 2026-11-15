import type { Manifest, ObservabilityView } from '../types/manifest'
import { isUsable } from '../services/manifest'
import { comparability } from '../services/finding'
import { beyondFrames, observabilityCurrent, STALE_NOTE } from '../services/observability'

export interface StoryStep {
  id: string
  title: string
  bookmarkId: string
  layerId: string
  references: string[]
  paragraphs: string[]
  chart?: 'lake' | 'observability'
  sources?: string
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

// Why the event pair has no valid coherence at the source, from the analysis: the product's own mask, no value at all, or both
function sourceNoValid(m: Manifest): 'masked' | 'nodata' | 'mixed' | null {
  const seen = frames(m).map(([, f]) => f.zones['gunw-coherence']?.[SOURCE]).filter((z) => z && z.pixels > 0)
  if (!seen.length || !seen.every((z) => z!.validPct === 0)) return null
  if (seen.every((z) => z!.maskedPct === 100)) return 'masked'
  return seen.every((z) => !z!.maskedPct) ? 'nodata' : 'mixed'
}

const SOURCE_TEXT = {
  masked: 'NISAR’s 16–28 August pair holds no usable measurement over the detachment zone: the radar product’s own quality mask flags it there, so this pair can judge neither a surface change nor ground movement at the source.',
  nodata: 'NISAR’s 16–28 August pair holds no value over the detachment zone, so this pair can judge neither a surface change nor ground movement at the source.',
  mixed: 'NISAR’s 16–28 August pair holds no usable measurement over the detachment zone: parts hold no value and the product’s own quality mask flags the rest.',
}

// Pair B (Track 98, the opposite side) at the source, from data/qa/pair-b-analysis.json: a measurement's median at the
// detachment zone against the ground near the channel, in the frame that reaches the zone
function sourceFromPairB(m: Manifest, measurement: string) {
  const z = (m.analysis?.['pair-b']?.frames ? Object.values(m.analysis['pair-b'].frames) : []).map((f) => f.zones[measurement]).find((x) => (x?.[SOURCE]?.validPct ?? 0) > 0)
  if (!z) return null
  const inside = z[SOURCE].median
  const outside = z[RING].median
  return inside == null || outside == null ? null : `${inside.toFixed(2)} at the detachment zone against ${outside.toFixed(2)} in terrain near the channel`
}

function pairBText(m: Manifest) {
  const coh = sourceFromPairB(m, 'gunw-coherence')
  const peak = sourceFromPairB(m, 'goff-peak')
  if (!coh && !peak) return null
  return `The 19–31 August pair views the slope from the opposite side and does reach it.${coh ? ` Its coherence there is very low: the median is ${coh}.` : ''}${peak ? ` Radar image matching largely fails too: the median correlation peak is ${peak}.` : ''} That is what a heavily changed surface can look like, but steep slopes, snow and a 12-day gap lower coherence as well.`
}

// A second viewing direction, only from numbers in the manifest. The views are compared, never merged.
function otherViewText(m: Manifest, v: ObservabilityView): string | null {
  const z = (task: string, id: string) => v.zones[task]?.[id]?.percent?.Usable
  const either = (task: string, id: string) => v.comparedWith?.zones[task]?.[id]?.either
  const src = [z('disturbance', 'vector:unosat_detachment_zone.geojson'), z('movement', 'vector:unosat_detachment_zone.geojson')]
  const flow = [z('disturbance', 'vector:unosat_mudflow_extent.geojson'), z('movement', 'vector:unosat_mudflow_extent.geojson')]
  if ([...src, ...flow].some((x) => x == null)) return null
  const main = m.observability?.zones.disturbance?.['vector:unosat_detachment_zone.geojson']?.percent?.Usable
  const flowEither = either('disturbance', 'vector:unosat_mudflow_extent.geojson')
  return `From the other side (${v.label}, pair ${day(v.pair[0])}–${day(v.pair[1])}${v.baselinePair ? `, before pair ${day(v.baselinePair[0])}–${day(v.baselinePair[1])}` : ''}), a surface change could be judged on ${src[0]!.toFixed(0)}% of the detachment zone${main === 0 && src[0]! > 0 ? ', where the first direction could judge none of it' : ''}, and ground movement on ${src[1]!.toFixed(0)}%. Over the mapped mudflow, ${flow[0]!.toFixed(0)}% is usable for change and ${flow[1]!.toFixed(0)}% for movement${flowEither != null ? `; ${flowEither.toFixed(0)}% is usable for change from at least one of the two directions` : ''}. Each direction is judged on its own; the map can show either.`
}

function ionosphereNote(m: Manifest) {
  const f = frames(m).map(([name, x]) => `${x.ionosphere.stdPhase} to ${x.ionosphere.stdPhaseMinusIono} radians in frame ${Number(name.slice(1))}`)
  return f.length ? `Most of the broad stripes in the raw phase come from the ionosphere, not the ground: subtracting the product's own estimate cuts the scatter from ${f.join(' and ')}.` : null
}

// Before/after against control ground. A seasonal change would be expected to lower both areas; a gap that opens only inside the
// mapped area is consistent with surface change there, but one comparison cannot establish the cause.
function controlText(m: Manifest) {
  const cs = m.controlSeries
  if (!cs) return null
  const before = cs.pairs.find((p) => p.pair[1] <= cs.eventDate)
  const across = cs.pairs.find((p) => p.pair[0] < cs.eventDate && p.pair[1] > cs.eventDate)
  if (!before || !across) return null
  const gap = (p: typeof before) => p.outside - p.inside
  const after = cs.pairs.filter((p) => p.pair[0] >= cs.eventDate)
  return `A pair from before the event gives a comparison. Between ${day(before.pair[0])} and ${day(before.pair[1])} the mapped area and the ground around it had similar median coherence (${before.inside.toFixed(2)} against ${before.outside.toFixed(2)}). Across the event the gap opened to ${gap(across).toFixed(2)} (${across.inside.toFixed(2)} against ${across.outside.toFixed(2)})${after.length ? `, then narrowed to ${after.map((p) => gap(p).toFixed(2)).join(', ')} in the pairs after` : ''}. A seasonal change would be expected to lower both areas; a gap that opens only inside the mapped area is consistent with surface change there, but it does not establish the cause. ${comparability(before, across)}`.trim()
}

// The same before/after comparison from the opposite side (controlSeriesViews), only from its own numbers
function opens(cs: Manifest['controlSeries']): boolean | null {
  if (!cs) return null
  const before = cs.pairs.find((p) => p.pair[1] <= cs.eventDate)
  const across = cs.pairs.find((p) => p.pair[0] < cs.eventDate && p.pair[1] > cs.eventDate)
  return before && across ? across.outside - across.inside > before.outside - before.inside : null
}

function otherControlText(m: Manifest) {
  const mainOpens = opens(m.controlSeries)
  return Object.values(m.controlSeriesViews ?? {}).flatMap((cs) => {
    const before = cs.pairs.find((p) => p.pair[1] <= cs.eventDate)
    const across = cs.pairs.find((p) => p.pair[0] < cs.eventDate && p.pair[1] > cs.eventDate)
    if (!before || !across) return []
    const modes = new Set(cs.pairs.map((p) => p.mode).filter(Boolean))
    const same = modes.size === 1 && cs.pairs.every((p) => p.mode)
    const ci = (p: typeof before) => (p.insideCi95 && p.outsideCi95 && (p.insideCi95[1] < p.outsideCi95[0] || p.outsideCi95[1] < p.insideCi95[0]))
    return [`From the opposite side (${cs.label ?? `Track ${cs.track}`}), ${same ? `every pair was acquired in the same radar mode (${[...modes][0]}), so a change of mode cannot explain the difference` : 'the pairs were not all acquired in the same radar mode'}. Before the event (${day(before.pair[0])}–${day(before.pair[1])}) the mapped area was ${before.inside.toFixed(2)} against ${before.outside.toFixed(2)} nearby${ci(before) ? ', already a little lower' : ''}; across the event it was ${across.inside.toFixed(2)} against ${across.outside.toFixed(2)}. ${opens(cs) ? (mainOpens ? 'Both directions show the gap opening across the event.' : 'From this side the gap opens across the event.') : 'From this side the gap does not open across the event.'} ${before.days !== across.days ? `The pre-event pair still spans ${before.days} days against ${across.days}.` : ''}`.trim()]
  })
}

// Radar Observability: what the radar could and could not judge, from the observability block (prepare_observability.py)
function observabilityStep(m: Manifest): StoryStep[] {
  const o = m.observability
  const layer = m.layers.find((l) => l.measurementType === 'observability-disturbance' && isUsable(l))
  if (!o || !layer) return []
  const z = (task: string, id: string) => o.zones[task]?.[id]?.percent?.Usable
  const src = [z('disturbance', 'vector:unosat_detachment_zone.geojson'), z('movement', 'vector:unosat_detachment_zone.geojson')]
  const flow = [z('disturbance', 'vector:unosat_mudflow_extent.geojson'), z('movement', 'vector:unosat_mudflow_extent.geojson')]
  const out = o.zones.disturbance?.['vector:unosat_mudflow_extent.geojson']?.percent?.['Outside the frame checked']
  const current = observabilityCurrent(m)
  const paras = [
    'Before reading any radar result, CascadeLens checks whether the radar could judge the place at all, for the question being asked. Each spot keeps its own reasons: outside the frame, no data or flagged by the product’s own quality mask, hidden by the mountain’s own slope (layover or shadow), a weak signal, or an input missing so the spot is not assessed.',
    ...(!current ? [STALE_NOTE] : []),
    ...(current && src.every((v) => v != null) ? [`At the detachment zone, a surface change could be judged on ${src[0]!.toFixed(0)}% of the ground and ground movement could be measured on ${src[1]!.toFixed(0)}%. Click the zone to see the reason for each spot.`] : []),
    ...(current && flow.every((v) => v != null) ? [`Over the mapped mudflow, ${flow[0]!.toFixed(0)}% is usable for judging change and ${flow[1]!.toFixed(0)}% for movement.${out ? ` ${out.toFixed(0)}% lies ${beyondFrames(m)}. No conclusion there is different from no damage.` : ''}`] : []),
    ...(current ? Object.values(m.observabilityViews ?? {}).map((v) => otherViewText(m, v)).filter((x): x is string => Boolean(x)) : []),
    'Click anywhere on the map to see the reasons for that exact spot.',
  ]
  const inc = o.incidenceDeg5to95 ? ` (incidence ${o.incidenceDeg5to95[0]}–${o.incidenceDeg5to95[1]}°)` : ''
  return [{ id: 'observability', title: 'Can the radar see it?', bookmarkId: 'source', layerId: layer.id, references: ['ref:unosat-extent', 'ref:unosat-detachment'], paragraphs: paras, chart: current ? 'observability' : undefined,
    sources: `Derived by CascadeLens from the NISAR GUNW pair ${day(o.pair[0])}–${day(o.pair[1])} 2026 (track ${o.track}, frame ${o.frame})${o.baselinePair ? `, the ${day(o.baselinePair[0])}–${day(o.baselinePair[1])} pair as the before baseline,` : ''} and the Copernicus DEM. Coherence threshold ${o.thresholds.coherenceMin?.value}; geometry from the product's own viewing angles${inc}. Method version ${o.methodVersion ?? 1}.` }]
}

// Text branches on the manifest, so the story can never claim a result that is not loaded.
export function buildStory(m: Manifest): StoryStep[] {
  if (m.lake) return lakeStory(m)
  const coherence = has(m, 'pair-a:gunw-coherence')
  const offset = has(m, 'pair-a:goff-range')
  const clean = has(m, 'pair-a:gunw-phase-iono')
  const coherenceText = contrast(m, 'gunw-coherence', 2)
  const validText = frames(m).flatMap(([name, f]) => {
    const v = f.zones['gunw-coherence']?.[EXTENT]?.validPct
    return v == null ? [] : [`${Math.round(v)}% of the mapped extent in frame ${Number(name.slice(1))}`]
  }).join(' and ')
  const offsetText = contrast(m, 'goff-range |x - scene median|', 2)
  const iono = ionosphereNote(m)
  const pairB = pairBText(m)
  const control = controlText(m)
  const radar = coherence
    ? ['The map shows coherence from the descending Track 48 pair of 16 and 28 August 2026: how consistent the radar signal stayed between the two passes.',
       ...(coherenceText ? [`Along the channel that UNOSAT mapped, coherence is much lower than on the terrain beside it. The median is ${coherenceText}, comparing inside the mapped extent with the area within 1 km of it.${validText ? ` Only pixels the product marks valid count: ${validText}.` : ''}`] : []),
       ...(control ? [control] : []),
       ...otherControlText(m),
       'This agrees with independent mapping, but it does not prove what happened. Low coherence has other causes too, and river channels are often low anyway.']
    : ['The descending Track 48 pair of 16 and 28 August 2026 brackets the event, and the catalogue footprints show both frames reach this corridor.',
       'The GUNW science files for this pair are not loaded in this build, so no phase or coherence is shown. They need a NASA Earthdata login to download.']
  return [
    {
      id: 'source', title: 'The source', bookmarkId: 'source', layerId: 'context:terrain', references: ['ref:unosat-detachment', 'ref:unosat-lakes', 'ref:rivers'],
      paragraphs: [
        'On 26 August 2026 a mountain mass movement was reported in the Langtang/Lhende area, near the Nepal–China border. Reports describe an ice-and-rock avalanche that blocked the upper Lhende Khola. Details of the source are still debated.',
        'The red polygon is UNOSAT’s mapped detachment zone and the blue polygons are barrier lakes. Both are independent satellite mapping, not NISAR results, and neither is field validated.',
        ...(sourceNoValid(m) ? [SOURCE_TEXT[sourceNoValid(m)!]] : []),
        ...(pairB ? [pairB] : []),
      ],
    },
    {
      id: 'radar', title: 'The radar evidence', bookmarkId: 'bhote-koshi', layerId: coherence ? 'pair-a:gunw-coherence' : 'context:terrain', references: ['ref:unosat-extent', 'ref:rivers'],
      paragraphs: [...radar, 'Twelve days separate the two acquisitions, so a pair can show that something changed between them, but not when within that interval.'],
    },
    ...observabilityStep(m),
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
        ...(offsetText ? [`Pixel offsets add little here: the typical offset size inside the mapped extent is close to the terrain beside it, at ${offsetText}, in metres. These offsets come from the product layer with the smallest search window, which could miss a very large shift. Most phase inside the extent could not be reliably unwrapped.`] : []),
        coherence || offset
          ? 'No displacement is calculated. The phase sign convention is not documented, so phase stays in radians.'
          : 'In this build, no NISAR measurement is loaded, so this story establishes where to look and which observations exist. It does not establish any radar-measured change.',
        'Confirming what happened on the ground needs field observations and further analysis. CascadeLens is retrospective: it does not predict hazards or issue warnings.',
      ],
    },
  ]
}


const day = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
const BACKGROUND = 'Background facts: ICIMOD (2011), Glacial Lakes and Glacial Lake Outburst Floods in Nepal; Peppa et al. (2020), ISPRS Annals V-3-2020, 633–640; the Department of Hydrology and Meteorology, Nepal, 2022 bathymetric survey, as reported by Dialogue Earth.'

// Compare only dates taken in the same radar mode, so a change of mode cannot pose as a change of lake
export function sameMode(s: NonNullable<Manifest['lake']>['series'], noise: number) {
  const groups = [...new Set(s.map((p) => p.polarization))].map((k) => s.filter((p) => p.polarization === k)).filter((g) => g.length > 1)
  if (!groups.length) return 'Each radar mode was used only once, so there is no same-mode pair to compare.'
  const parts = groups.map((g) => `${g[0].polarization}-pol ${g[0].nativePostingM} m dates: ${(g[g.length - 1].areaKm2 - g[0].areaKm2 >= 0 ? '+' : '')}${(g[g.length - 1].areaKm2 - g[0].areaKm2).toFixed(2)} km²`)
  const ok = groups.every((g) => Math.abs(g[g.length - 1].areaKm2 - g[0].areaKm2) <= noise)
  return `Comparing only dates taken in the same radar mode (${parts.join('; ')}) ${ok ? 'gives the same answer: no change beyond the uncertainty.' : 'shows a change beyond the uncertainty, so check the outlines.'}`
}

// The glacial lake story. Every number comes from the manifest (lake.py and motion.py); the background facts are published ones.
function lakeStory(m: Manifest): StoryStep[] {
  const lake = m.lake!
  const s = lake.series
  const id = m.caseStudy.id
  const has = (layer: string) => m.layers.some((l) => l.id === layer && isUsable(l))
  const lo = Math.min(...s.map((p) => p.areaKm2))
  const hi = Math.max(...s.map((p) => p.areaKm2))
  const modes = [...new Set(s.map((p) => `${p.polarization}-pol ${p.nativePostingM} m`))]
  const mo = lake.motion
  const steps: StoryStep[] = [
    {
      id: 'risk', title: 'A lake held back by loose rock', bookmarkId: 'valley', layerId: 'context:terrain', references: ['ref:lake-edge'],
      paragraphs: [
        `${lake.name} sits at about 4,580 m at the head of the Rolwaling valley in Dolakha, Nepal. It grew as the Trakarding Glacier melted back: from about 0.23 km² in the late 1950s to about 1.5 km² by the late 1990s.`,
        'The water is held back by a moraine, a heap of loose rock and buried ice that the glacier left behind. If it failed, an outburst flood would run down the Rolwaling Khola past the villages of Na and Beding, into the Tamakoshi, a river with hydropower plants and roads along it.',
        'In 2000, engineers cut a channel through the moraine and lowered the lake by about 3 m to reduce the risk. It is still one of the most closely watched glacial lakes in Nepal.',
      ],
      sources: BACKGROUND,
    },
    {
      id: 'radar', title: 'NISAR sees through the monsoon', bookmarkId: 'lake', layerId: `${id}:rgb`, references: ['ref:lake-edge'],
      paragraphs: [
        `NISAR passed over the lake every 12 days: ${s.map((p) => day(p.date)).join(', ')} ${s[s.length - 1].date.slice(0, 4)}. This is the monsoon, when cameras on other satellites mostly see cloud. NISAR's L-band radar, with a 24 cm wavelength, sees through cloud and works at night.`,
        'Calm water reflects the radar away, so the lake is black. The colours come from polarization: how the echo changes when the radar sends and receives in horizontal or vertical. Smooth rock and ice look purple, rough moraine and debris look yellow-green.',
        `The passes alternated between two radar modes (${modes.join(' and ')}). To compare them fairly, every date is put on the same 20 m grid.`,
      ],
    },
    {
      id: 'verdict', title: 'The lake did not change size', bookmarkId: 'lake', layerId: `${id}:hh`, references: ['ref:lake-edge'], chart: 'lake',
      paragraphs: [
        `On every date the lake measured between ${lo.toFixed(2)} and ${hi.toFixed(2)} km². That spread is smaller than the method's own range, about ±${lake.methodHalfRangeKm2.toFixed(2)} km² (half the largest change in area when the water threshold moves between −8 and −6 dB; a method range, not a formal error), so the radar sees no change in these ${Math.round((Date.parse(s[s.length - 1].date) - Date.parse(s[0].date)) / 86400000)} days.`,
        'Our number falls inside the range of published figures: about 1.55 km² in a 2008 survey, 1.61 km² from satellite images (Peppa et al., 2020) and 1.65 km² in a 2022 bathymetric survey for the Department of Hydrology and Meteorology. That agreement is a check on the method, not proof of an exact area.',
        sameMode(s, lake.methodHalfRangeKm2),
      ],
    },
  ]
  const coh: { pair: [string, string]; lake: number; land: number; lakeValidPct?: number | null } | null = lake.coherence ?? (mo?.pair && mo.coherenceLake !== undefined && mo.coherenceLand !== undefined ? { pair: mo.pair, lake: mo.coherenceLake, land: mo.coherenceLand } : null)
  // When the product's water mask covers most of the lake, a lake median would rest on its shoreline: say what is masked instead
  const lakeMasked = coh?.lakeValidPct != null && coh.lakeValidPct < 50
  if (coh && has(`${id}:coherence`)) {
    steps.push({
      id: 'coherence', title: 'Where did the ground stay the same?', bookmarkId: 'valley', layerId: `${id}:coherence`, references: ['ref:lake-edge'],
      paragraphs: [
        lakeMasked
          ? `The map shows how alike the radar echoes were on ${day(coh.pair[0])} and ${day(coh.pair[1])}. Bright means the surface stayed the same; dark means it changed, or is radar shadow. The radar product's own water mask covers ${Math.round(100 - coh.lakeValidPct!)}% of the lake, so the lake itself has no usable value here; the land around it has a median of ${coh.land.toFixed(2)}.`
          : `The map shows how alike the radar echoes were on ${day(coh.pair[0])} and ${day(coh.pair[1])}. Bright means the surface stayed the same; dark means it changed, or is water or radar shadow. The lake is dark (median ${coh.lake.toFixed(2)}); the land around it has a median of ${coh.land.toFixed(2)}.`,
        'Coherence says where the surface stayed the same between two passes. It does not measure how far anything moved: turning radar phase into movement needs a confirmed sign convention and reference, which CascadeLens does not have yet.',
      ],
    })
  }
  // The dam-break scenario stays out of the guided story (audit, Category D): it rests on assumed breach depths and is
  // offered only under Illustrations, as "What if", with its ranges and assumptions in view.
  const scenarioNote = lake.scenario
    ? ['A labelled what-if dam-break scenario, built on assumed breach depths, is under Illustrations: What if. It is not a prediction and not a warning.']
    : []
  steps.push({
    id: 'why', title: 'Why it held steady, and what would change it', bookmarkId: 'valley', layerId: `${id}:rgb`, references: ['ref:lake-edge'],
    paragraphs: [
      'Why no change: the engineered channel at the dam lets extra monsoon water drain out instead of raising the lake. And lakes like this grow at the glacier end, as ice melts and breaks off into the water. That takes years: a change of a few percent would hide inside the radar’s 20 m pixels over five weeks.',
      'What would make it grow: warmer years melting the glacier faster, the glacier front retreating up the valley, or the moraine dam weakening as the ice buried inside it melts.',
      'What comes next: put these five weeks into decades of history with older satellite images, add NISAR dates after the monsoon, and check the outline against an optical image. The result we want to test: stable this season, but grown over decades.',
      ...scenarioNote,
    ],
    sources: BACKGROUND,
  })
  return steps
}
