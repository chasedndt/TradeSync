import { fibLevels } from '../fib'
import { formatChartPrice } from '../format'
import { clipLine, expandBox, type Box, type Segment } from '../geometry'
import type { ShapeLayout } from '../hitTest'
import { LABEL_FONT, labelBox, paintLabel, strokeSegments } from './paint'
import { nonNull, projectAnchors } from './project'
import type { ShapeRenderer } from './types'

interface FibLine {
  segment: Segment | null
  text: string
  box: Box
}

interface FibLayout extends ShapeLayout {
  lines: FibLine[]
  diagonal: Segment | null
}

/** Retracement levels across the move from the first anchor to the second, each with its price. */
export const fibRetracementRenderer: ShapeRenderer<FibLayout> = {
  layout(shape, context) {
    const points = projectAnchors(shape, context.view)
    if (!points || points.length < 2) return null
    const [a, b] = points
    const [start, end] = shape.anchors
    const left = Math.min(a.x, b.x)
    const right = Math.max(a.x, b.x)
    const bounds = expandBox(context.pane, 4)

    const lines: FibLine[] = []
    for (const { level, price } of fibLevels(start.price, end.price)) {
      const y = context.view.priceToY(price)
      if (y == null) continue
      const text = `${level} (${formatChartPrice(price)})`
      lines.push({
        segment: clipLine({ x: left, y }, { x: right, y }, bounds, 'segment'),
        text,
        box: labelBox({ x: left + 2, y: y - 2 }, context.measureText(text, LABEL_FONT), 'left', 'bottom'),
      })
    }
    const diagonal = clipLine(a, b, bounds, 'segment')
    return {
      handles: [a, b],
      segments: [...lines.map((line) => line.segment).filter(nonNull), ...(diagonal ? [diagonal] : [])],
      labels: lines.map((line) => line.box),
      lines,
      diagonal,
    }
  },
  draw(ctx, shape, layout) {
    strokeSegments(ctx, layout.lines.map((line) => line.segment).filter(nonNull), shape.style)
    if (layout.diagonal) strokeSegments(ctx, [layout.diagonal], { ...shape.style, width: 1, dashed: true })
    for (const line of layout.lines) paintLabel(ctx, line.text, line.box, shape.style.colour)
  },
}
