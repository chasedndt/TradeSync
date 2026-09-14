import { distanceToSegment } from './geometry'
import type { PixelPoint } from './types'

/** Indices kept by Ramer-Douglas-Peucker at this tolerance, in order, always with both ends. */
export function rdpIndices(points: readonly PixelPoint[], epsilon: number): number[] {
  const count = points.length
  if (count <= 2) return points.map((_, index) => index)

  const keep = new Uint8Array(count)
  keep[0] = 1
  keep[count - 1] = 1
  // An explicit stack rather than recursion: a long stroke would otherwise
  // recurse once per retained point.
  const stack: Array<[number, number]> = [[0, count - 1]]
  while (stack.length) {
    const [start, end] = stack.pop()!
    let farthest = -1
    let farthestDistance = epsilon
    for (let i = start + 1; i < end; i++) {
      const d = distanceToSegment(points[i], points[start], points[end])
      if (d > farthestDistance) {
        farthest = i
        farthestDistance = d
      }
    }
    if (farthest !== -1) {
      keep[farthest] = 1
      stack.push([start, farthest], [farthest, end])
    }
  }

  const kept: number[] = []
  keep.forEach((flag, index) => {
    if (flag) kept.push(index)
  })
  return kept
}

/**
 * A freehand stroke reduced to at most `maxPoints`: first at `epsilon` pixels,
 * loosening the tolerance until it fits. Returns the indices to keep.
 */
export function simplifyStroke(
  points: readonly PixelPoint[],
  { epsilon = 1, maxPoints = 400 }: { epsilon?: number; maxPoints?: number } = {},
): number[] {
  const ceiling = Math.max(2, maxPoints)
  let tolerance = Math.max(epsilon, 0.01)
  let kept = rdpIndices(points, tolerance)
  while (kept.length > ceiling) {
    tolerance *= 1.5
    kept = rdpIndices(points, tolerance)
  }
  return kept
}
