import type { Layer } from '../types/manifest'

export interface Explanation {
  what: string
  measures: string
  inspect: string
  establishes: string
}

const offsets = (axis: string): Explanation => ({
  what: `The ${axis} component of NISAR pixel offsets. Radar images from two dates are matched patch by patch, and this is how far the patches appear to have shifted.`,
  measures: 'An image-feature shift in radar coordinates, in metres. It is a separate measurement from interferometric phase, and it still works where phase breaks down.',
  inspect: 'Check SNR and the correlation peak at the same location. These offsets are raw: they are not culled or filtered, so outliers are expected.',
  establishes: 'A candidate shift in one radar direction. It is not an east/west or north/south movement, and quality must be examined before reading it as surface motion.',
})

export const EXPLANATIONS: Record<string, Explanation> = {
  'gunw-phase': {
    what: 'A NISAR interferometric phase product derived from two radar observations of the same ground.',
    measures: 'The phase relationship between the two acquisitions, in radians, under the product’s own processing convention.',
    inspect: 'Coherence and connected components show whether the phase is suitable for interpretation.',
    establishes: 'Radar-measured evidence. Physical displacement and its cause would need further processing, quality checks and interpretation. No displacement is calculated here.',
  },
  'gunw-coherence': {
    what: 'How consistent the radar signal stayed between the two observations, from 0 to 1.',
    measures: 'Signal consistency, not movement. Vegetation, snow, water and surface disruption can all lower it.',
    inspect: 'Use it beside phase: low values limit how far the phase at that location can be trusted.',
    establishes: 'The reliability of the phase. Low coherence alone does not prove a landslide or show its extent.',
  },
  'gunw-cc': {
    what: 'Regions the phase unwrapper treated as connected.',
    measures: 'Arbitrary labels. A number has no size or order: it only names a region.',
    inspect: 'Phase comparisons are safest within one component, because separate components may differ by an unknown whole number of cycles. Label 0 means the phase could not be reliably unwrapped.',
    establishes: 'How phase can be compared across the scene. It says nothing about the ground itself.',
  },
  'gunw-phase-iono': {
    what: 'The unwrapped phase after subtracting the ionosphere estimate published in the same product. CascadeLens calculates this layer.',
    measures: 'What remains of the phase once the broad atmospheric pattern is taken out. It still includes troposphere, terrain and noise effects.',
    inspect: 'Compare it with the raw phase. Patterns that survive the subtraction are worth a closer look, and coherence shows where to trust them.',
    establishes: 'A clearer view of local phase patterns. It is still phase, not displacement.',
  },
  'gunw-iono': {
    what: 'The estimate of how much the ionosphere changed the phase between the two radar passes, published in the product.',
    measures: 'A smooth, large-scale phase pattern in radians, caused by the atmosphere high above the ground.',
    inspect: 'Compare it with the phase. Broad patterns that appear in both are more likely atmospheric than ground movement.',
    establishes: 'Why some phase patterns should not be read as surface change. It is shown for comparison and is not removed from the phase here.',
  },
  'goff-range': offsets('slant-range'),
  'goff-azimuth': offsets('along-track'),
  'goff-snr': {
    what: 'The signal-to-noise ratio of each pixel-offset estimate.',
    measures: 'How strongly the matched feature stood out from noise.',
    inspect: 'Compare it with the range and along-track offsets at the same location.',
    establishes: 'Confidence in an offset estimate, not any movement.',
  },
  'goff-peak': {
    what: 'The height of the normalised correlation peak found while matching image patches.',
    measures: 'Match quality. A low peak suggests a weak or ambiguous match.',
    inspect: 'Use it with SNR to judge an offset value.',
    establishes: 'Confidence in an offset estimate, not any movement.',
  },
  'gcov-backscatter': {
    what: 'Terrain-corrected radar backscatter from a single NISAR acquisition.',
    measures: 'How strongly the surface returned the radar signal, shown as gamma-0 in decibels.',
    inspect: 'Read each date on its own, with its orbit direction. Ascending and descending images view slopes from opposite sides.',
    establishes: 'Surface-response context. It is not a quantitative flood, landslide or damage map, and the two dates are not differenced.',
  },
  elevation: {
    what: 'Copernicus DEM GLO-30, a global digital surface model.',
    measures: 'Surface height above the EGM2008 geoid, in metres.',
    inspect: 'Use it for geographic setting: valley shape, slopes and the drop from source area to river corridor.',
    establishes: 'Pre-event terrain only. It records nothing about the 2026 event, and it is not a NISAR measurement.',
  },
  reference: {
    what: 'Independent satellite mapping by UNOSAT, not a NISAR result.',
    measures: 'What UNOSAT analysts mapped from their own sensors, dates and method.',
    inspect: 'Check the source, date and validation status before comparing it with radar evidence.',
    establishes: 'Context. UNOSAT records its event layers as not yet field validated, so they are not ground truth.',
  },
  'reference-s1': {
    what: 'An analysis of Copernicus Sentinel-1 radar images, made by another organisation. Sentinel-1 is a different mission from NISAR.',
    measures: 'Change in C-band radar backscatter around the event. NISAR flies an L-band radar, so the two do not sense the surface in the same way.',
    inspect: 'Use it to see where independent evidence points, and check its limits. It is stronger near built areas than in steep terrain.',
    establishes: 'A preliminary indication of change, not confirmed damage. An empty area does not prove there was no damage.',
  },
  'reference-context': {
    what: 'General geographic reference from a public dataset.',
    measures: 'Mapped features such as rivers, roads, settlements or boundaries.',
    inspect: 'Use it to find your way around the corridor.',
    establishes: 'Geographic context only. It is not evidence about the event.',
  },
  preview: {
    what: 'A browse picture published with a NISAR product, shown because the science file could not be used.',
    measures: 'Nothing that can be read here. It is a coloured image, not a set of measurements.',
    inspect: 'Use it to see roughly where the product covers.',
    establishes: 'Only that the product exists and roughly where it falls. Do not draw quantitative conclusions from it.',
  },
}

export function explanationFor(l: Pick<Layer, 'measurementType' | 'mission' | 'explanation'>): Explanation {
  if (l.explanation) return l.explanation
  if (l.measurementType !== 'reference') return EXPLANATIONS[l.measurementType] ?? EXPLANATIONS.reference
  if (l.mission === 'UNOSAT') return EXPLANATIONS.reference
  return EXPLANATIONS[l.mission === 'Sentinel-1' ? 'reference-s1' : 'reference-context']
}
