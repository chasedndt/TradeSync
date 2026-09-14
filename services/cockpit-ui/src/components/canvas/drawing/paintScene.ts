import { expandBox } from './geometry'
import { layoutBounds, type LaidOutShape, type ShapeLayout } from './hitTest'
import { RENDERERS } from './renderers'
import { outlineBox, paintHandles } from './renderers/paint'
import type { LayoutContext } from './renderers/types'
import type { ChartShape } from './types'

export interface SceneState {
  shapes: readonly ChartShape[]
  selectedId: string | null
  hidden: boolean
  /** A shape being dragged, drawn in place of its stored version. */
  dragged: ChartShape | null
  /** A shape being placed or a stroke being drawn. */
  preview: ChartShape | null
  /** The last measurement, kept until the next click. */
  ruler: ChartShape | null
}

export const EMPTY_SCENE: SceneState = {
  shapes: [],
  selectedId: null,
  hidden: false,
  dragged: null,
  preview: null,
  ruler: null,
}

/** Paint every shape, the selection, and anything being placed. Returns what was drawn, for hit testing. */
export function paintScene(ctx: CanvasRenderingContext2D, context: LayoutContext, scene: SceneState): LaidOutShape[] {
  const laidOut: LaidOutShape[] = []
  if (!scene.hidden) {
    let selected: { shape: ChartShape; layout: ShapeLayout } | null = null
    for (const stored of scene.shapes) {
      const shape = scene.dragged?.id === stored.id ? scene.dragged : stored
      const layout = paintShape(ctx, context, shape)
      if (!layout) continue
      laidOut.push({ id: shape.id, layout })
      if (shape.id === scene.selectedId) selected = { shape, layout }
    }
    if (selected) paintSelection(ctx, selected.layout, selected.shape.style.colour)
  }
  for (const transient of [scene.ruler, scene.preview]) {
    if (!transient) continue
    const layout = paintShape(ctx, context, transient)
    if (layout) paintHandles(ctx, layout.handles, transient.style.colour)
  }
  return laidOut
}

function paintShape(ctx: CanvasRenderingContext2D, context: LayoutContext, shape: ChartShape): ShapeLayout | null {
  const renderer = RENDERERS[shape.kind]
  const layout = renderer.layout(shape, context)
  if (layout) renderer.draw(ctx, shape, layout)
  return layout
}

function paintSelection(ctx: CanvasRenderingContext2D, layout: ShapeLayout, colour: string): void {
  if (layout.handles.length) {
    paintHandles(ctx, layout.handles, colour)
    return
  }
  const bounds = layoutBounds(layout)
  if (bounds) outlineBox(ctx, expandBox(bounds, 4), colour)
}
