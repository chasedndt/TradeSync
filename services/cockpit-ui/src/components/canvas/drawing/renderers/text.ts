import type { Box } from '../geometry'
import type { ShapeLayout } from '../hitTest'
import { PANE_INK } from './paint'
import type { ShapeRenderer } from './types'
import { wrapText } from './wrapText'

export const TEXT_FONT = '13px "Segoe UI Variable", "Segoe UI", Inter, ui-sans-serif, system-ui, sans-serif'
const LINE_HEIGHT = 18
const PADDING = 6
const MAX_WIDTH = 260

interface TextLayout extends ShapeLayout {
  lines: string[]
  box: Box
}

/** Text written on the chart, above and to the right of its anchor. Notes are drawn the same way. */
export const textRenderer: ShapeRenderer<TextLayout> = {
  layout(shape, context) {
    const anchor = shape.anchors[0]
    const at = anchor ? context.view.toPixel(anchor) : null
    if (!at || !shape.label) return null
    const measure = (text: string) => context.measureText(text, TEXT_FONT)
    const lines = wrapText(shape.label, MAX_WIDTH, measure)
    const width = Math.max(0, ...lines.map(measure))
    const box = {
      left: at.x,
      top: at.y - lines.length * LINE_HEIGHT - PADDING,
      right: at.x + width + PADDING * 2,
      bottom: at.y,
    }
    return { handles: [], segments: [], labels: [box], lines, box }
  },
  draw(ctx, shape, layout) {
    const { box, lines } = layout
    ctx.save()
    ctx.globalAlpha = 0.72
    ctx.fillStyle = PANE_INK
    ctx.fillRect(box.left, box.top, box.right - box.left, box.bottom - box.top)
    ctx.globalAlpha = 1
    // An edge in the drawing's colour ties the text to its anchor corner.
    ctx.fillStyle = shape.style.colour
    ctx.fillRect(box.left, box.top, 2, box.bottom - box.top)
    ctx.font = TEXT_FONT
    ctx.textAlign = 'left'
    ctx.textBaseline = 'top'
    lines.forEach((line, index) => ctx.fillText(line, box.left + PADDING, box.top + PADDING / 2 + index * LINE_HEIGHT))
    ctx.restore()
  },
}
