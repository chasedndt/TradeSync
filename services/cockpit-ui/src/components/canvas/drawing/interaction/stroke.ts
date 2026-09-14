import { simplifyStroke } from '../simplify'
import type { Anchor, PixelPoint } from '../types'

/** The most points a stored stroke keeps; the server refuses more. */
export const MAX_STROKE_POINTS = 400

/**
 * A freehand stroke as it is stored: simplified in screen space, where the
 * operator judged its shape, to at most 400 points, in whole seconds, and with
 * no point repeated.
 */
export function strokeAnchors(anchors: readonly Anchor[], pixels: readonly PixelPoint[]): Anchor[] {
  const stored: Anchor[] = []
  for (const index of simplifyStroke(pixels, { epsilon: 1, maxPoints: MAX_STROKE_POINTS })) {
    const anchor = { time: Math.round(anchors[index].time), price: anchors[index].price }
    const previous = stored[stored.length - 1]
    if (!previous || previous.time !== anchor.time || previous.price !== anchor.price) stored.push(anchor)
  }
  return stored
}
