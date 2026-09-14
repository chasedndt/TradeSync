import type { Box } from '../geometry'
import type { ChartShape, PixelPoint } from '../types'
import { LABEL_FONT, labelBox, paintLabel } from './paint'
import type { LayoutContext } from './types'

/**
 * A stored label shows as a caption with the drawing's version, as the canvas
 * has always shown it: "v3" means the drawing has been revised twice. Shapes
 * from the tool rail are saved without a label, so they carry no caption.
 */
export function captionText(shape: ChartShape): string | null {
  if (!shape.label) return null
  return shape.version ? `${shape.label} · v${shape.version}` : shape.label
}

export function captionBox(
  shape: ChartShape,
  at: PixelPoint,
  align: 'left' | 'right',
  baseline: 'top' | 'bottom',
  context: LayoutContext,
): Box | undefined {
  const text = captionText(shape)
  return text ? labelBox(at, context.measureText(text, LABEL_FONT), align, baseline) : undefined
}

export function paintCaption(ctx: CanvasRenderingContext2D, shape: ChartShape, box: Box | undefined): void {
  const text = captionText(shape)
  if (text && box) paintLabel(ctx, text, box, shape.style.colour)
}
