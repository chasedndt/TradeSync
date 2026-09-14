import { boxFromPoints, expandBox, intersectBox, type Box } from '../geometry'
import type { ShapeLayout } from '../hitTest'
import { describeMeasurement, measure } from '../measure'
import type { PixelPoint } from '../types'
import { fillBox, LABEL_FONT, PANE_INK } from './paint'
import { projectAnchors } from './project'
import type { ShapeRenderer } from './types'

const RISING = '#3fb27f'
const FALLING = '#e0574a'
const LINE_HEIGHT = 15

interface RulerLayout extends ShapeLayout {
  from: PixelPoint
  to: PixelPoint
  fill: Box | null
  lines: [string, string]
  badge: Box
  rising: boolean
}

/** The measuring ruler: price change and percentage, bars and time. Shown while measuring, never stored. */
export const rulerRenderer: ShapeRenderer<RulerLayout> = {
  layout(shape, context) {
    const points = projectAnchors(shape, context.view)
    if (!points || points.length < 2) return null
    const [from, to] = points
    const [start, end] = shape.anchors
    const lines = describeMeasurement(measure(start, end, context.view.axis))
    const rising = end.price >= start.price
    const box = boxFromPoints(from, to)
    const width = Math.max(...lines.map((line) => context.measureText(line, LABEL_FONT))) + 16
    const height = LINE_HEIGHT * 2 + 8
    const centre = (box.left + box.right) / 2
    const top = rising ? box.top - height - 6 : box.bottom + 6
    return {
      handles: [],
      segments: [],
      from,
      to,
      lines,
      rising,
      fill: intersectBox(box, expandBox(context.pane, 4)),
      badge: { left: centre - width / 2, top, right: centre + width / 2, bottom: top + height },
    }
  },
  draw(ctx, _shape, layout) {
    const { from, to, badge, lines } = layout
    const colour = layout.rising ? RISING : FALLING
    fillBox(ctx, layout.fill, colour, 0.16)

    ctx.save()
    ctx.setLineDash([])
    ctx.lineWidth = 1
    ctx.strokeStyle = colour
    ctx.fillStyle = colour
    const middleX = (from.x + to.x) / 2
    const middleY = (from.y + to.y) / 2
    arrow(ctx, { x: middleX, y: from.y }, { x: middleX, y: to.y })
    arrow(ctx, { x: from.x, y: middleY }, { x: to.x, y: middleY })

    ctx.globalAlpha = 0.92
    ctx.fillRect(badge.left, badge.top, badge.right - badge.left, badge.bottom - badge.top)
    ctx.globalAlpha = 1
    ctx.fillStyle = PANE_INK
    ctx.font = LABEL_FONT
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    lines.forEach((line, index) => ctx.fillText(line, (badge.left + badge.right) / 2, badge.top + 4 + index * LINE_HEIGHT))
    ctx.restore()
  },
}

function arrow(ctx: CanvasRenderingContext2D, from: PixelPoint, to: PixelPoint): void {
  const length = Math.hypot(to.x - from.x, to.y - from.y)
  if (length < 1) return
  ctx.beginPath()
  ctx.moveTo(from.x, from.y)
  ctx.lineTo(to.x, to.y)
  ctx.stroke()
  const ux = (to.x - from.x) / length
  const uy = (to.y - from.y) / length
  const head = Math.min(7, length / 2)
  ctx.beginPath()
  ctx.moveTo(to.x, to.y)
  ctx.lineTo(to.x - ux * head - uy * head * 0.6, to.y - uy * head + ux * head * 0.6)
  ctx.lineTo(to.x - ux * head + uy * head * 0.6, to.y - uy * head - ux * head * 0.6)
  ctx.closePath()
  ctx.fill()
}
