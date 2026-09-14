import { boxFromPoints, clipLine, expandBox, intersectBox, type Box } from '../geometry'
import type { ShapeLayout } from '../hitTest'
import { captionBox, paintCaption } from './caption'
import { fillBox, strokeSegments } from './paint'
import { nonNull, projectAnchors } from './project'
import type { ShapeRenderer } from './types'

export interface BoxLayout extends ShapeLayout {
  /** The part of the rectangle inside the pane, for the fill. */
  fill: Box | null
  caption?: Box
}

/** A rectangle between two opposite corners, filled lightly so it reads as a zone. */
export function boxRenderer(fillAlpha: number): ShapeRenderer<BoxLayout> {
  return {
    layout(shape, context) {
      const points = projectAnchors(shape, context.view)
      if (!points || points.length < 2) return null
      const [a, b] = points
      const box = boxFromPoints(a, b)
      const bounds = expandBox(context.pane, 4)
      const corners = [
        { x: box.left, y: box.top },
        { x: box.right, y: box.top },
        { x: box.right, y: box.bottom },
        { x: box.left, y: box.bottom },
      ]
      const edges = corners
        .map((corner, i) => clipLine(corner, corners[(i + 1) % corners.length], bounds, 'segment'))
        .filter(nonNull)
      const caption = captionBox(shape, { x: box.left + 4, y: box.top - 4 }, 'left', 'bottom', context)
      return {
        handles: [a, b],
        segments: edges,
        area: { box, filled: true },
        labels: caption ? [caption] : [],
        fill: intersectBox(box, bounds),
        caption,
      }
    },
    draw(ctx, shape, layout) {
      fillBox(ctx, layout.fill, shape.style.colour, fillAlpha)
      strokeSegments(ctx, layout.segments, shape.style)
      paintCaption(ctx, shape, layout.caption)
    },
  }
}
