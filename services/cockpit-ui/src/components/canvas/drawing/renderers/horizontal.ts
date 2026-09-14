import { captionBox, paintCaption } from './caption'
import type { LineLayout } from './line'
import { strokeSegments } from './paint'
import type { ShapeRenderer } from './types'

/** A price level across the whole pane. Its time anchor is kept but not drawn. */
export const horizontalRenderer: ShapeRenderer<LineLayout> = {
  layout(shape, context) {
    const price = shape.anchors[0]?.price
    const y = price == null ? null : context.view.priceToY(price)
    if (y == null) return null
    const { pane } = context
    const caption = captionBox(shape, { x: pane.right - 8, y: y - 3 }, 'right', 'bottom', context)
    return {
      handles: [{ x: (pane.left + pane.right) / 2, y }],
      segments: [[{ x: pane.left, y }, { x: pane.right, y }]],
      labels: caption ? [caption] : [],
      caption,
    }
  },
  draw(ctx, shape, layout) {
    strokeSegments(ctx, layout.segments, shape.style)
    paintCaption(ctx, shape, layout.caption)
  },
}
