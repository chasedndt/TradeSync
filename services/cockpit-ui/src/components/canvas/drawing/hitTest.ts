import {
  distance,
  distanceToBoxEdge,
  distanceToSegment,
  expandBox,
  insideBox,
  type Box,
  type Segment,
} from './geometry'
import type { HitPart, PixelPoint, ShapeHit } from './types'

/** Pixels either side of a stroke that still count as touching it. */
export const HIT_TOLERANCE = 6
/** Radius of an anchor handle, as drawn. */
export const HANDLE_RADIUS = 5

/** Where a shape sits in the pane, as its renderer laid it out. Hit testing reads only this. */
export interface ShapeLayout {
  /** One per draggable anchor, in anchor order; empty when none can be dragged alone. */
  handles: PixelPoint[]
  /** Straight strokes, already clipped to the pane. */
  segments: Segment[]
  /** A freehand path. */
  path?: PixelPoint[]
  /** A rectangle: a filled one is hit anywhere inside, an outline only near an edge. */
  area?: { box: Box; filled: boolean }
  /** Text and captions, which count as part of the shape. */
  labels?: Box[]
}

const BODY: HitPart = { kind: 'body' }

export function hitLayout(layout: ShapeLayout, p: PixelPoint, tolerance = HIT_TOLERANCE): HitPart | null {
  for (let index = 0; index < layout.handles.length; index++) {
    if (distance(p, layout.handles[index]) <= HANDLE_RADIUS + 2) return { kind: 'handle', index }
  }
  if (layout.segments.some(([a, b]) => distanceToSegment(p, a, b) <= tolerance)) return BODY

  const path = layout.path
  if (path?.length === 1 && distance(p, path[0]) <= tolerance) return BODY
  if (path) {
    for (let i = 1; i < path.length; i++) {
      if (distanceToSegment(p, path[i - 1], path[i]) <= tolerance) return BODY
    }
  }

  const area = layout.area
  if (area && (area.filled ? insideBox(p, expandBox(area.box, tolerance)) : distanceToBoxEdge(p, area.box) <= tolerance)) {
    return BODY
  }
  if (layout.labels?.some((box) => insideBox(p, expandBox(box, 2)))) return BODY
  return null
}

/** The smallest box around everything a layout draws, or null when it draws nothing. */
export function layoutBounds(layout: ShapeLayout): Box | null {
  const points: PixelPoint[] = []
  for (const [a, b] of layout.segments) points.push(a, b)
  if (layout.path) points.push(...layout.path)
  const boxes = [...(layout.area ? [layout.area.box] : []), ...(layout.labels ?? [])]
  for (const box of boxes) points.push({ x: box.left, y: box.top }, { x: box.right, y: box.bottom })
  if (!points.length) return null
  return {
    left: Math.min(...points.map((p) => p.x)),
    top: Math.min(...points.map((p) => p.y)),
    right: Math.max(...points.map((p) => p.x)),
    bottom: Math.max(...points.map((p) => p.y)),
  }
}

export interface LaidOutShape {
  id: string
  layout: ShapeLayout
}

/**
 * The shape under a point.
 *
 * Later shapes are drawn over earlier ones, so they are tested first. The
 * selected shape is tested before all of them, so its handles stay reachable
 * where another shape overlaps it.
 */
export function hitShapes(
  shapes: readonly LaidOutShape[],
  p: PixelPoint,
  selectedId: string | null,
  tolerance = HIT_TOLERANCE,
): ShapeHit | null {
  const selected = selectedId ? shapes.find((shape) => shape.id === selectedId) : undefined
  if (selected) {
    const part = hitLayout(selected.layout, p, tolerance)
    if (part) return { id: selected.id, part }
  }
  for (let i = shapes.length - 1; i >= 0; i--) {
    const shape = shapes[i]
    if (shape === selected) continue
    const part = hitLayout(shape.layout, p, tolerance)
    if (part) return { id: shape.id, part }
  }
  return null
}
