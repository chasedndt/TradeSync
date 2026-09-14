import type { ShapeLayout } from '../hitTest'
import type { PixelPoint } from '../types'
import { strokePath } from './paint'
import { projectAnchors } from './project'
import type { ShapeRenderer } from './types'

interface PencilLayout extends ShapeLayout {
  path: PixelPoint[]
}

/** A freehand stroke through its simplified points. It moves whole; it has no handles. */
export const pencilRenderer: ShapeRenderer<PencilLayout> = {
  layout(shape, context) {
    const path = projectAnchors(shape, context.view)
    return path && path.length >= 2 ? { handles: [], segments: [], path } : null
  },
  draw(ctx, shape, layout) {
    strokePath(ctx, layout.path, shape.style)
  },
}
