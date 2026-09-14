import { clipLine, expandBox } from '../geometry'
import { captionBox, paintCaption } from './caption'
import type { LineLayout } from './line'
import { strokeSegments } from './paint'
import type { ShapeRenderer } from './types'

/** A price level from its anchor to the right edge of the pane. */
export const horizontalRayRenderer: ShapeRenderer<LineLayout> = {
  layout(shape, context) {
    const anchor = shape.anchors[0]
    const start = anchor ? context.view.toPixel(anchor) : null
    if (!start) return null
    const { pane } = context
    const stroke = clipLine(start, { x: start.x + 1, y: start.y }, expandBox(pane, 4), 'ray')
    const caption = captionBox(shape, { x: pane.right - 8, y: start.y - 3 }, 'right', 'bottom', context)
    return { handles: [start], segments: stroke ? [stroke] : [], labels: caption ? [caption] : [], caption }
  },
  draw(ctx, shape, layout) {
    strokeSegments(ctx, layout.segments, shape.style)
    paintCaption(ctx, shape, layout.caption)
  },
}
