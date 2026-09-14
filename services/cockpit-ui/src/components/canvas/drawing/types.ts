import type { DrawingKind, DrawingStyle } from '../../../api/drawingTypes'

export type { DrawingStyle }

/** A point in chart terms: UNIX seconds and price. Stored drawings keep whole seconds. */
export interface Anchor {
  time: number
  price: number
}

/** A point in the pane, in CSS pixels from its top-left corner. */
export interface PixelPoint {
  x: number
  y: number
}

/** A kind that is stored. `range` and `note` predate the tool rail and still render. */
export type SavedKind = DrawingKind

/** Everything the layer draws, including the measuring ruler, which is never stored. */
export type ShapeKind = SavedKind | 'measure'

/** A tool on the rail: the cursor, or the kind of shape it places. */
export type ToolId = 'cursor' | Exclude<ShapeKind, 'range' | 'note'>

export interface ChartShape {
  /** The stored drawing's id, or a local id for a preview. */
  id: string
  kind: ShapeKind
  anchors: Anchor[]
  style: DrawingStyle
  label: string
  /** Absent on a preview. */
  version?: number
  /** The interval the drawing was made on. It shows on every interval. */
  interval?: string
}

export type HitPart = { kind: 'body' } | { kind: 'handle'; index: number }

export interface ShapeHit {
  id: string
  part: HitPart
}
