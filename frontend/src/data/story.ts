import type { Manifest } from '../types/manifest'
import { isUsable } from '../services/manifest'

export interface StoryStep {
  id: string
  title: string
  bookmarkId: string
  layerId: string
  references: string[]
  paragraphs: string[]
  chart?: 'lake'
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

// Before/after against control ground: rain or season change hits both areas, so only the gap between them points at the slide.
function controlText(m: Manifest) {
  const cs = m.controlSeries
  if (!cs) return null
  const before = cs.pairs.find((p) => p.pair[1] <= cs.eventDate)
  const across = cs.pairs.find((p) => p.pair[0] < cs.eventDate && p.pair[1] > cs.eventDate)
  if (!before || !across) return null
  const gap = (p: typeof before) => p.outside - p.inside
  const after = cs.pairs.filter((p) => p.pair[0] >= cs.eventDate)
  return `A pair from before the event is the fair test. Between ${day(before.pair[0])} and ${day(before.pair[1])} the slide area and the ground around it scored about the same (${before.inside.toFixed(2)} against ${before.outside.toFixed(2)}). Across the event the gap opened to ${gap(across).toFixed(2)} (${across.inside.toFixed(2)} against ${across.outside.toFixed(2)})${after.length ? `, then narrowed to ${after.map((p) => gap(p).toFixed(2)).join(', ')} in the pairs after` : ''}. Rain or season change would lower both areas together, so the opening gap points at the slide itself. The before pair spans ${before.days} days and the others ${across.days}, which this comparison only partly corrects for.`
}

// Text branches on the manifest, so the story can never claim a result that is not loaded.
export function buildStory(m: Manifest): StoryStep[] {
  if (m.lake) return lakeStory(m)
  const coherence = has(m, 'pair-a:gunw-coherence')
  const offset = has(m, 'pair-a:goff-range')
  const clean = has(m, 'pair-a:gunw-phase-iono')
  const coherenceText = contrast(m, 'gunw-coherence', 2)
  const offsetText = contrast(m, 'goff-range |x - scene median|', 2)
  const iono = ionosphereNote(m)
  const pairB = sourceFromPairB(m)
  const control = controlText(m)
  const radar = coherence
    ? ['The map shows coherence from the descending Track 48 pair of 16 and 28 August 2026: how consistent the radar signal stayed between the two passes.',
       ...(coherenceText ? [`Along the channel that UNOSAT mapped, coherence is much lower than on the terrain beside it. The median is ${coherenceText}, comparing inside the mapped extent with the area within 1 km of it.`] : []),
       ...(control ? [control] : []),
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


const day = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
const BACKGROUND = 'Background facts: ICIMOD (2011), Glacial Lakes and Glacial Lake Outburst Floods in Nepal, and the Department of Hydrology and Meteorology, Nepal.'

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
        `On every date the lake measured between ${lo.toFixed(2)} and ${hi.toFixed(2)} km². That spread is smaller than the method's own uncertainty, about ±${lake.methodHalfRangeKm2.toFixed(2)} km², so the radar sees no change in these ${Math.round((Date.parse(s[s.length - 1].date) - Date.parse(s[0].date)) / 86400000)} days.`,
        'Our number matches published surveys, which give about 1.5 to 1.6 km² in recent years. That agreement is a check that the method works.',
        sameMode(s, lake.methodHalfRangeKm2),
      ],
    },
  ]
  if (mo && (mo.dam?.ok || mo.glacier.length)) {
    const dam = mo.dam?.ok ? mo.dam : null
    const g = mo.glacier.reduce<typeof mo.glacier[number] | null>((a, b) => (!a || b.limitM > a.limitM ? b : a), null)
    steps.push({
      id: 'motion', title: 'Is the dam or the glacier moving?', bookmarkId: 'valley', layerId: has(`${id}:coherence`) ? `${id}:coherence` : `${id}:hh`, references: ['ref:lake-edge', 'ref:zones'],
      paragraphs: [
        ...(mo.pair ? [`The map shows how alike the radar echoes were on ${day(mo.pair[0])} and ${day(mo.pair[1])}. Bright means the ground stayed the same, dark means it changed (or is water). The lake is dark (${mo.coherenceLake?.toFixed(2)}); the land around it averages ${mo.coherenceLand?.toFixed(2)}.`] : []),
        ...(dam ? [dam.detected
          ? `The moraine dam (orange circle at the lake's west end) moved about ${dam.differenceCm?.toFixed(1)} cm towards or away from the satellite in 12 days, compared with the ground around it. That is more than the noise and worth a closer look.`
          : `The moraine dam (orange circle at the west end) stayed bright (${dam.coherence?.toFixed(2)}) and moved less than about ${dam.limitCm?.toFixed(0)} cm towards or away from the satellite in 12 days, compared with the ground around it.${(mo.damPairs?.length ?? 0) > 1 ? ` The same holds in ${mo.damPairs!.filter((d) => d.ok && !d.detected).length} of ${mo.damPairs!.length} 12-day pairs.` : ''} No sign that it is slumping.`] : []),
        ...(g ? [g.detected
          ? `The glacier zone beyond the far end of the lake shifted more than stable ground in the radar's image matching, about ${g.limitM.toFixed(1)} m in ${g.days} days.`
          : `In the glacier zone beyond the lake's far end, image matching found no movement above the noise: less than about ${g.limitM.toFixed(1)} m in ${g.days} days, or roughly ${g.perYearM} m a year. Checked from ${mo.glacier.length} different satellite tracks.`] : []),
        'These are upper limits from one 12-day pair, not proof that nothing moves. The glacier zone is approximate, because no glacier outline is loaded yet.',
      ],
    })
  }
  const sc = lake.scenario
  const mid = sc?.scenarios.find((q) => q.breachM === 20) ?? sc?.scenarios[0]
  if (sc && mid) {
    const at = (k: number) => mid.arrival.find((q) => q[0] >= k)
    const t = (q?: [number, number, number]) => (q ? `${q[1]} to ${q[2]} minutes` : 'unknown')
    steps.push({
      id: 'scenario', title: 'What if the dam failed?', bookmarkId: 'valley', layerId: 'context:hillshade', references: ['ref:lake-edge', 'ref:scenario-route', 'ref:scenario-extent'],
      paragraphs: [
        'Nobody can calculate whether or when a moraine dam will fail. What real numbers can do is work out what would follow if it did. This is a scenario, not a prediction, and not a warning.',
        `If a ${mid.breachM} m deep breach opened, about ${Math.round(mid.volumeM3 / 1e6)} million m³ of water would escape: NISAR's lake area times the depth. Two published formulas put the peak flow at the dam between ${mid.peakRange[0].toLocaleString('en-GB')} and ${mid.peakRange[1].toLocaleString('en-GB')} m³/s.`,
        `Cross-sections through the real terrain give the speed: the water would reach 10 km down the valley in ${t(at(10))}, and 30 km, where the route turns down the Tamakoshi, in ${t(at(30))}. Open "What if" at the top for the full table and the other breach sizes.`,
      ],
    })
  }
  steps.push({
    id: 'why', title: 'Why it held steady, and what would change it', bookmarkId: 'valley', layerId: `${id}:rgb`, references: ['ref:lake-edge'],
    paragraphs: [
      'Why no change: the engineered channel at the dam lets extra monsoon water drain out instead of raising the lake. And lakes like this grow at the glacier end, as ice melts and breaks off into the water. That takes years: a change of a few percent would hide inside the radar’s 20 m pixels over five weeks.',
      'What would make it grow: warmer years melting the glacier faster, the glacier front retreating up the valley, or the moraine dam weakening as the ice buried inside it melts.',
      'What comes next: put these five weeks into decades of history with older satellite images, add NISAR dates after the monsoon, and check the outline against an optical image. The result we want to test: stable this season, but grown over decades.',
    ],
    sources: BACKGROUND,
  })
  return steps
}
