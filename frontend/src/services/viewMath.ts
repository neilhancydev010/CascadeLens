// The maths behind the View controls: where a slider puts the centre of the view, and back again.
// One axis at a time, in any straight-line unit (the map uses Web Mercator units, the Compare picture uses fractions of its width).
// `lo` and `hi` are the edges of the area the view must stay inside, and `view` is how much of that axis the view shows.

/** True when the view shows less than the whole range, so there is somewhere to pan to. */
export function canPan(lo: number, hi: number, view: number): boolean {
  return view < hi - lo - 1e-12
}

/** Keeps a centre where the view stays inside [lo, hi]. When the view is as wide as the range or wider, the only answer is the middle. */
export function clampCentre(centre: number, lo: number, hi: number, view: number): number {
  if (!canPan(lo, hi, view)) return (lo + hi) / 2
  const half = view / 2
  return Math.min(hi - half, Math.max(lo + half, centre))
}

/** Slider position t, from 0 (the low edge) to 1 (the high edge), to a centre that keeps the view inside the range. */
export function sliderToCentre(t: number, lo: number, hi: number, view: number): number {
  if (!canPan(lo, hi, view)) return (lo + hi) / 2
  const s = Math.min(1, Math.max(0, t))
  const half = view / 2
  return lo + half + s * (hi - lo - view)
}

/** A centre back to a slider position from 0 to 1. A centre outside the allowed span reads as the nearer end. */
export function centreToSlider(centre: number, lo: number, hi: number, view: number): number {
  if (!canPan(lo, hi, view)) return 0.5
  const half = view / 2
  return Math.min(1, Math.max(0, (centre - lo - half) / (hi - lo - view)))
}

/** The deepest zoom the slider offers: the layer's own deepest tiles, but never more than five levels past the whole-area view. */
export function zoomCeiling(fitZoom: number, tileMaxZoom: number | undefined): number {
  const cap = fitZoom + 5
  if (tileMaxZoom === undefined || !Number.isFinite(tileMaxZoom)) return cap
  return Math.max(fitZoom, Math.min(cap, tileMaxZoom))
}

// Web Mercator in units of the whole world (0 to 1), the projection the map draws in. y grows southwards.
export const mercX = (lng: number) => (lng + 180) / 360
export const mercY = (lat: number) => (1 - Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)) / Math.PI) / 2
export const lngOf = (x: number) => x * 360 - 180
export const latOf = (y: number) => (Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180) / Math.PI
