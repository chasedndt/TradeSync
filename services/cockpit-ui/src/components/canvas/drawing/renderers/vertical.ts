import { captionBox, paintCaption } from './caption'
import type { LineLayout } from './line'
import { strokeSegments } from './paint'
import type { ShapeRenderer } from './types'

/** A moment, top to bottom of the pane. Its price anchor is kept but not drawn. */
export const verticalRenderer: ShapeRenderer<LineLayout> = {
  layout(shape, context) {
    const time = shape.anchors[0]?.time
    const x = time == null ? null : context.view.timeToX(time)
    if (x == null) return null
    const { pane } = context
    const caption = captionBox(shape, { x: x + 4, y: pane.top + 4 }, 'left', 'top', context)
    return {
      handles: [{ x, y: (pane.top + pane.bottom) / 2 }],
      segments: [[{ x, y: pane.top }, { x, y: pane.bottom }]],
      labels: caption ? [caption] : [],
      caption,
    }
  },
  draw(ctx, shape, layout) {
    strokeSegments(ctx, layout.segments, shape.style)
    paintCaption(ctx, shape, layout.caption)
  },
}
