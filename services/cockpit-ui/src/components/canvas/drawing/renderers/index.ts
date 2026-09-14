import type { ShapeKind } from '../types'
import { extendedLineRenderer } from './extendedLine'
import { fibRetracementRenderer } from './fibRetracement'
import { horizontalRenderer } from './horizontal'
import { horizontalRayRenderer } from './horizontalRay'
import { pencilRenderer } from './pencil'
import { rangeRenderer } from './range'
import { rayRenderer } from './ray'
import { rectangleRenderer } from './rectangle'
import { rulerRenderer } from './ruler'
import { textRenderer } from './text'
import { trendlineRenderer } from './trendline'
import type { ShapeRenderer } from './types'
import { verticalRenderer } from './vertical'

/** One renderer per kind. A note is drawn as text; the ruler is drawn but never stored. */
export const RENDERERS: Record<ShapeKind, ShapeRenderer> = {
  trendline: trendlineRenderer,
  ray: rayRenderer,
  extended_line: extendedLineRenderer,
  horizontal: horizontalRenderer,
  horizontal_ray: horizontalRayRenderer,
  vertical: verticalRenderer,
  rectangle: rectangleRenderer,
  range: rangeRenderer,
  fib_retracement: fibRetracementRenderer,
  pencil: pencilRenderer,
  text: textRenderer,
  note: textRenderer,
  measure: rulerRenderer,
}
