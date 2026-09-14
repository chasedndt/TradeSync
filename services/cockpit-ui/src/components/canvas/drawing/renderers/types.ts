import type { Box } from '../geometry'
import type { ShapeLayout } from '../hitTest'
import type { Projection } from '../projection'
import type { ChartShape } from '../types'

export interface LayoutContext {
  view: Projection
  /** The pane, in media pixels from its top-left corner. */
  pane: Box
  /** Width of `text` in pixels when drawn in `font`. */
  measureText(text: string, font: string): number
}

/** Lays out and paints one kind of shape. The registry maps each kind to one of these. */
export interface ShapeRenderer<L extends ShapeLayout = ShapeLayout> {
  /** Pixel geometry for the shape on this chart, or null when it cannot be placed. */
  layout(shape: ChartShape, context: LayoutContext): L | null
  /** Paint a laid-out shape. Selection handles are painted by the layer, not here. */
  draw(ctx: CanvasRenderingContext2D, shape: ChartShape, layout: L): void
}
