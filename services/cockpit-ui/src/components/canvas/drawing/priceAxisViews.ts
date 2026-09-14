import type { ISeriesPrimitiveAxisView } from 'lightweight-charts'
import { formatChartPrice } from './format'
import type { ChartShape, ShapeKind } from './types'

const PRICE_LABELLED: ReadonlySet<ShapeKind> = new Set<ShapeKind>(['horizontal', 'horizontal_ray'])

/**
 * Price-axis labels for horizontal lines, as the old price lines had.
 *
 * Each label reads its shape through `current` whenever the axis is painted,
 * so a line being dragged carries its label with it.
 */
export function priceAxisViews(
  shapes: readonly ChartShape[],
  current: (id: string) => ChartShape | undefined,
  priceToY: (price: number) => number | null,
): ISeriesPrimitiveAxisView[] {
  return shapes
    .filter((shape) => PRICE_LABELLED.has(shape.kind))
    .map((shape) => {
      const price = () => current(shape.id)?.anchors[0]?.price
      return {
        coordinate: () => {
          const value = price()
          return (value == null ? null : priceToY(value)) ?? -1000
        },
        text: () => {
          const value = price()
          return value == null ? '' : formatChartPrice(value)
        },
        textColor: () => '#07111f',
        backColor: () => current(shape.id)?.style.colour ?? shape.style.colour,
        visible: () => price() != null,
      }
    })
}
