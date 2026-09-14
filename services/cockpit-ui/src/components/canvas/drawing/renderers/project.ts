import type { Projection } from '../projection'
import type { ChartShape, PixelPoint } from '../types'

/** Every anchor of a shape in pane pixels, or null if any cannot be placed. */
export function projectAnchors(shape: ChartShape, view: Projection): PixelPoint[] | null {
  const points: PixelPoint[] = []
  for (const anchor of shape.anchors) {
    const point = view.toPixel(anchor)
    if (!point) return null
    points.push(point)
  }
  return points
}

export function nonNull<T>(value: T | null | undefined): value is T {
  return value != null
}
