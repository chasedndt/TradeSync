import type { ShapeKind, ToolId } from './types'

/** How a tool places its shape. */
export type Placement = 'one-click' | 'two-click' | 'stroke' | 'text'

export const PLACEMENT: Record<Exclude<ToolId, 'cursor'>, Placement> = {
  trendline: 'two-click',
  ray: 'two-click',
  extended_line: 'two-click',
  rectangle: 'two-click',
  fib_retracement: 'two-click',
  measure: 'two-click',
  horizontal: 'one-click',
  horizontal_ray: 'one-click',
  vertical: 'one-click',
  pencil: 'stroke',
  text: 'text',
}

/** Kinds whose second anchor Shift snaps to 0, 45 or 90 degrees. */
export const ANGLE_SNAPPED: ReadonlySet<ShapeKind> = new Set<ShapeKind>(['trendline', 'ray', 'extended_line'])

export const KIND_NAMES: Record<ShapeKind, string> = {
  trendline: 'Trend line',
  ray: 'Ray',
  extended_line: 'Extended line',
  horizontal: 'Horizontal line',
  horizontal_ray: 'Horizontal ray',
  vertical: 'Vertical line',
  rectangle: 'Rectangle',
  range: 'Range',
  fib_retracement: 'Fib retracement',
  measure: 'Measure',
  pencil: 'Pencil',
  text: 'Text',
  note: 'Note',
}
