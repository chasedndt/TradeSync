/** Colour scales for heatmaps drawn over a dark chart: dim and translucent when small, bright and opaque when large. */

export type Rgba = [number, number, number, number]

const RESTING: [number, number, number][] = [
  [20, 11, 52], [58, 12, 96], [106, 23, 110], [157, 44, 102], [207, 68, 70], [241, 110, 30], [250, 170, 20], [252, 236, 140],
]
const LIQUIDATION: [number, number, number][] = [
  [18, 32, 72], [26, 84, 140], [22, 150, 160], [80, 200, 120], [200, 225, 60], [255, 190, 40], [255, 120, 40], [255, 245, 200],
]

function sample(stops: [number, number, number][], t: number): Rgba {
  const x = Math.max(0, Math.min(1, t)) * (stops.length - 1)
  const i = Math.min(stops.length - 2, Math.floor(x))
  const f = x - i
  const [a, b] = [stops[i], stops[i + 1]]
  return [Math.round(a[0] + (b[0] - a[0]) * f), Math.round(a[1] + (b[1] - a[1]) * f), Math.round(a[2] + (b[2] - a[2]) * f), 0.18 + 0.78 * Math.max(0, Math.min(1, t))]
}

export const restingColour = (t: number): Rgba => sample(RESTING, t)
export const liquidationColour = (t: number): Rgba => sample(LIQUIDATION, t)

/** Log scale against a reference value (the 95th percentile, say), so a few huge cells do not wash out the rest. */
export const intensity = (value: number, reference: number): number =>
  reference > 0 ? Math.min(1, Math.log1p(value) / Math.log1p(reference)) : 0

export const cssColour = ([r, g, b, a]: Rgba): string => `rgba(${r}, ${g}, ${b}, ${a.toFixed(3)})`

/** A CSS gradient of the scale, for the legend. */
export const gradient = (colour: (t: number) => Rgba): string =>
  `linear-gradient(90deg, ${[0, 0.2, 0.4, 0.6, 0.8, 1].map((t) => cssColour(colour(t))).join(', ')})`
