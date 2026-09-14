import type { Anchor, ChartShape, DrawingStyle, HitPart, PixelPoint, SavedKind, ToolId } from '../types'

/** The page state each pointer event is judged against. */
export interface InteractionState {
  tool: ToolId
  style: DrawingStyle
  selectedId: string | null
  hidden: boolean
  locked: boolean
}

/** What the interaction reads from, and asks of, the canvas page. */
export interface InteractionHost {
  state(): InteractionState
  /** A stored shape that can be edited; undefined for one still being saved. */
  shape(id: string): ChartShape | undefined
  select(id: string | null): void
  create(kind: SavedKind, anchors: Anchor[]): void
  move(id: string, anchors: Anchor[]): void
  /** A shape was placed: the rail goes back to the cursor, as on TradingView. */
  placed(): void
  requestText(anchor: Anchor, at: PixelPoint): void
}

export type PlacingTool = Exclude<ToolId, 'cursor'>

export interface DragGesture {
  type: 'drag'
  pointerId: number
  id: string
  part: HitPart
  down: PixelPoint
  original: Anchor[]
  /** The anchors so far, once the press has travelled far enough to be a drag. */
  moved: Anchor[] | null
}

export interface StrokeGesture {
  type: 'stroke'
  pointerId: number
  anchors: Anchor[]
  pixels: PixelPoint[]
}

export interface PlaceGesture {
  type: 'place'
  pointerId: number
  down: PixelPoint
  /** This press set a two-click shape's first anchor. */
  startedDraft: boolean
}

export type Gesture = DragGesture | StrokeGesture | PlaceGesture
