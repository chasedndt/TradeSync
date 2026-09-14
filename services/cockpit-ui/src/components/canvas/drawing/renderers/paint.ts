import type { Box, Segment } from '../geometry'
import { HANDLE_RADIUS } from '../hitTest'
import type { DrawingStyle, PixelPoint } from '../types'

export const LABEL_FONT = '11px ui-monospace, SFMono-Regular, Menlo, monospace'
export const LABEL_HEIGHT = 16
export const LABEL_PADDING = 4
/** The canvas page colour, used behind text so it reads over candles. */
export const PANE_INK = '#07111f'
const LABEL_BACKING = 'rgba(7, 17, 31, 0.82)'

function withStroke(ctx: CanvasRenderingContext2D, style: DrawingStyle, paint: () => void): void {
  ctx.save()
  ctx.strokeStyle = style.colour
  ctx.lineWidth = style.width
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.setLineDash(style.dashed ? [6, 4] : [])
  paint()
  ctx.restore()
}

export function strokeSegments(ctx: CanvasRenderingContext2D, segments: readonly Segment[], style: DrawingStyle): void {
  if (!segments.length) return
  withStroke(ctx, style, () => {
    ctx.beginPath()
    for (const [a, b] of segments) {
      ctx.moveTo(a.x, a.y)
      ctx.lineTo(b.x, b.y)
    }
    ctx.stroke()
  })
}

export function strokePath(ctx: CanvasRenderingContext2D, path: readonly PixelPoint[], style: DrawingStyle): void {
  if (path.length < 2) return
  withStroke(ctx, style, () => {
    ctx.beginPath()
    ctx.moveTo(path[0].x, path[0].y)
    for (let i = 1; i < path.length; i++) ctx.lineTo(path[i].x, path[i].y)
    ctx.stroke()
  })
}

export function fillBox(ctx: CanvasRenderingContext2D, box: Box | null, colour: string, alpha: number): void {
  if (!box) return
  ctx.save()
  ctx.globalAlpha = alpha
  ctx.fillStyle = colour
  ctx.fillRect(box.left, box.top, box.right - box.left, box.bottom - box.top)
  ctx.restore()
}

/** The box a one-line label occupies when anchored at `at`. */
export function labelBox(
  at: PixelPoint,
  textWidth: number,
  align: 'left' | 'right' | 'center',
  baseline: 'top' | 'bottom' | 'middle',
): Box {
  const width = textWidth + LABEL_PADDING * 2
  const left = align === 'left' ? at.x : align === 'right' ? at.x - width : at.x - width / 2
  const top = baseline === 'top' ? at.y : baseline === 'bottom' ? at.y - LABEL_HEIGHT : at.y - LABEL_HEIGHT / 2
  return { left, top, right: left + width, bottom: top + LABEL_HEIGHT }
}

export function paintLabel(ctx: CanvasRenderingContext2D, text: string, box: Box, colour: string): void {
  ctx.save()
  ctx.fillStyle = LABEL_BACKING
  ctx.fillRect(box.left, box.top, box.right - box.left, box.bottom - box.top)
  ctx.font = LABEL_FONT
  ctx.fillStyle = colour
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, box.left + LABEL_PADDING, (box.top + box.bottom) / 2 + 0.5)
  ctx.restore()
}

export function paintHandles(ctx: CanvasRenderingContext2D, handles: readonly PixelPoint[], colour: string): void {
  if (!handles.length) return
  ctx.save()
  ctx.setLineDash([])
  ctx.lineWidth = 1.5
  ctx.strokeStyle = colour
  ctx.fillStyle = PANE_INK
  for (const handle of handles) {
    ctx.beginPath()
    ctx.arc(handle.x, handle.y, HANDLE_RADIUS, 0, Math.PI * 2)
    ctx.fill()
    ctx.stroke()
  }
  ctx.restore()
}

/** A thin dashed frame marking a selected shape that has no handles. */
export function outlineBox(ctx: CanvasRenderingContext2D, box: Box, colour: string): void {
  ctx.save()
  ctx.setLineDash([3, 3])
  ctx.lineWidth = 1
  ctx.strokeStyle = colour
  ctx.strokeRect(box.left, box.top, box.right - box.left, box.bottom - box.top)
  ctx.restore()
}
