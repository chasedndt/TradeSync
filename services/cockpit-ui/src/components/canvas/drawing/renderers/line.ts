import { clipLine, expandBox, type Box } from '../geometry'
import type { ShapeLayout } from '../hitTest'
import { captionBox, paintCaption } from './caption'
import { strokeSegments } from './paint'
import { projectAnchors } from './project'
import type { ShapeRenderer } from './types'

export interface LineLayout extends ShapeLayout {
  caption?: Box
}

/** A straight line through two anchors: a segment, a ray from the first, or a line both ways. */
export function lineRenderer(mode: 'segment' | 'ray' | 'line'): ShapeRenderer<LineLayout> {
  return {
    layout(shape, context) {
      const points = projectAnchors(shape, context.view)
      if (!points || points.length < 2) return null
      const [a, b] = points
      const stroke = clipLine(a, b, expandBox(context.pane, 4), mode)
      const caption = captionBox(shape, { x: b.x + 6, y: b.y - 4 }, 'left', 'bottom', context)
      return { handles: [a, b], segments: stroke ? [stroke] : [], labels: caption ? [caption] : [], caption }
    },
    draw(ctx, shape, layout) {
      strokeSegments(ctx, layout.segments, shape.style)
      paintCaption(ctx, shape, layout.caption)
    },
  }
}
