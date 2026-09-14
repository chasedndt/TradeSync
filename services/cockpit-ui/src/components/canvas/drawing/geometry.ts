import type { PixelPoint } from './types'

export interface Box {
  left: number
  top: number
  right: number
  bottom: number
}

export type Segment = readonly [PixelPoint, PixelPoint]

export function distance(a: PixelPoint, b: PixelPoint): number {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

/** Shortest distance from `p` to the segment from `a` to `b`. */
export function distanceToSegment(p: PixelPoint, a: PixelPoint, b: PixelPoint): number {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const lengthSquared = dx * dx + dy * dy
  if (lengthSquared === 0) return distance(p, a)
  const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / lengthSquared))
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy))
}

export function boxFromPoints(a: PixelPoint, b: PixelPoint): Box {
  return {
    left: Math.min(a.x, b.x),
    top: Math.min(a.y, b.y),
    right: Math.max(a.x, b.x),
    bottom: Math.max(a.y, b.y),
  }
}

export function expandBox(box: Box, by: number): Box {
  return { left: box.left - by, top: box.top - by, right: box.right + by, bottom: box.bottom + by }
}

export function insideBox(p: PixelPoint, box: Box): boolean {
  return p.x >= box.left && p.x <= box.right && p.y >= box.top && p.y <= box.bottom
}

/** The overlap of two boxes, or null when they do not overlap. */
export function intersectBox(a: Box, b: Box): Box | null {
  const box = {
    left: Math.max(a.left, b.left),
    top: Math.max(a.top, b.top),
    right: Math.min(a.right, b.right),
    bottom: Math.min(a.bottom, b.bottom),
  }
  return box.left < box.right && box.top < box.bottom ? box : null
}

/** Distance from `p` to the nearest edge of `box`; zero on an edge. */
export function distanceToBoxEdge(p: PixelPoint, box: Box): number {
  const topLeft = { x: box.left, y: box.top }
  const topRight = { x: box.right, y: box.top }
  const bottomRight = { x: box.right, y: box.bottom }
  const bottomLeft = { x: box.left, y: box.bottom }
  return Math.min(
    distanceToSegment(p, topLeft, topRight),
    distanceToSegment(p, topRight, bottomRight),
    distanceToSegment(p, bottomRight, bottomLeft),
    distanceToSegment(p, bottomLeft, topLeft),
  )
}

/**
 * The part of the line through `a` and `b` that lies inside `box`.
 *
 * `segment` keeps only a to b, `ray` starts at a and runs on through b, and
 * `line` runs both ways. Returns null when none of it is inside. Clipping
 * before stroking keeps a shape whose anchors are far off screen from being
 * drawn at coordinates the canvas cannot represent accurately.
 */
export function clipLine(
  a: PixelPoint,
  b: PixelPoint,
  box: Box,
  mode: 'segment' | 'ray' | 'line',
): Segment | null {
  const dx = b.x - a.x
  const dy = b.y - a.y
  if (dx === 0 && dy === 0) {
    return mode === 'segment' && insideBox(a, box) ? [a, a] : null
  }
  // Liang-Barsky: narrow the parameter range edge by edge.
  let t0 = mode === 'line' ? -Infinity : 0
  let t1 = mode === 'segment' ? 1 : Infinity
  const edges: ReadonlyArray<readonly [number, number]> = [
    [-dx, a.x - box.left],
    [dx, box.right - a.x],
    [-dy, a.y - box.top],
    [dy, box.bottom - a.y],
  ]
  for (const [p, q] of edges) {
    if (p === 0) {
      if (q < 0) return null
      continue
    }
    const t = q / p
    if (p < 0) t0 = Math.max(t0, t)
    else t1 = Math.min(t1, t)
    if (t0 > t1) return null
  }
  return [
    { x: a.x + t0 * dx, y: a.y + t0 * dy },
    { x: a.x + t1 * dx, y: a.y + t1 * dy },
  ]
}
