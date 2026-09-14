import type { Drawing, DrawingInput } from '../../../api/drawingTypes'
import type { ChartShape, DrawingStyle, SavedKind } from './types'

export const DEFAULT_COLOUR = '#e3b23c'
export const DEFAULT_STYLE: DrawingStyle = { colour: DEFAULT_COLOUR, width: 2, dashed: false }

const HEX_COLOUR = /^#[0-9a-f]{6}$/i

export type SavedShape = ChartShape & { kind: SavedKind }

export function isSavedShape(shape: ChartShape): shape is SavedShape {
  return shape.kind !== 'measure'
}

/** A style as the server accepts it: colour #rrggbb, whole width 1-4, dashed true or false. */
export function isDrawingStyle(value: unknown): value is DrawingStyle {
  if (!value || typeof value !== 'object') return false
  const { colour, width, dashed } = value as Record<string, unknown>
  return (
    typeof colour === 'string' &&
    HEX_COLOUR.test(colour) &&
    typeof width === 'number' &&
    Number.isInteger(width) &&
    width >= 1 &&
    width <= 4 &&
    typeof dashed === 'boolean'
  )
}

/**
 * A stored drawing as the layer draws it.
 *
 * Versions saved before styles existed keep the look they always had: dashed,
 * in their stored colour or the canvas amber.
 */
export function shapeFromDrawing(drawing: Drawing): ChartShape {
  return {
    id: drawing.drawing_id,
    kind: drawing.kind,
    anchors: drawing.points.map((point) => ({ time: point.time_s, price: point.price })),
    style: drawing.style ?? legacyStyle(drawing.kind, drawing.colour),
    label: drawing.label ?? '',
    version: drawing.version,
    interval: drawing.interval,
  }
}

function legacyStyle(kind: SavedKind, colour: string | undefined): DrawingStyle {
  return {
    colour: colour && HEX_COLOUR.test(colour) ? colour.toLowerCase() : DEFAULT_COLOUR,
    width: kind === 'trendline' ? 2 : 1,
    dashed: true,
  }
}

/** Ten significant figures: enough for any venue price, without float noise. */
export function cleanPrice(price: number): number {
  return Number(price.toPrecision(10))
}

/**
 * The payload that stores a shape. A drawing keeps the interval it was made
 * on, even when it is moved from another interval's chart.
 */
export function drawingInput(shape: SavedShape, symbol: string, currentInterval: string): DrawingInput {
  return {
    symbol,
    interval: shape.interval ?? currentInterval,
    kind: shape.kind,
    points: shape.anchors.map((anchor) => ({ time_s: Math.round(anchor.time), price: cleanPrice(anchor.price) })),
    label: shape.label,
    style: shape.style,
  }
}
