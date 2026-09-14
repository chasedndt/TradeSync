import type { BarPrice, Coordinate, Logical } from 'lightweight-charts'
import { logicalToTime, timeToLogical, type TimeAxis } from './anchors'
import type { Anchor, PixelPoint } from './types'

/** The part of the chart a projection reads for x. */
export interface TimeSource {
  timeScale(): { logicalToCoordinate(logical: Logical): Coordinate | null }
}

/** The part of the series a projection reads for y. */
export interface PriceSource {
  priceToCoordinate(price: number): Coordinate | null
  coordinateToPrice(coordinate: number): BarPrice | null
}

export interface Projection {
  readonly axis: TimeAxis
  timeToX(time: number): number | null
  xToLogical(x: number): number
  priceToY(price: number): number | null
  yToPrice(y: number): number | null
  toPixel(anchor: Anchor): PixelPoint | null
  /** The anchor under a pane point; `snapToBar` moves it to the nearest bar's time. */
  toAnchor(point: PixelPoint, snapToBar: boolean): Anchor | null
}

/**
 * Pane coordinates for anchors, read from the chart as it is now.
 *
 * Lightweight Charts 4.2 returns 0 from `logicalToCoordinate` for a fractional
 * index and only whole bars from `coordinateToLogical`, so the x mapping is
 * read from two whole bars and extended linearly. The library's own mapping is
 * linear in the index, so this agrees with it everywhere, past the last bar too.
 */
export function createProjection(chart: TimeSource, series: PriceSource, axis: TimeAxis): Projection | null {
  const timeScale = chart.timeScale()
  const x0 = timeScale.logicalToCoordinate(0 as Logical)
  const x1 = timeScale.logicalToCoordinate(1 as Logical)
  if (x0 == null || x1 == null || x1 === x0) return null
  return linearProjection(x0, x1 - x0, series, axis)
}

export function linearProjection(x0: number, spacing: number, prices: PriceSource, axis: TimeAxis): Projection {
  const xToLogical = (x: number) => (x - x0) / spacing
  const priceToY = (price: number): number | null => prices.priceToCoordinate(price)
  const yToPrice = (y: number): number | null => prices.coordinateToPrice(y)
  const timeToX = (time: number): number | null => {
    const logical = timeToLogical(time, axis)
    return logical == null ? null : x0 + logical * spacing
  }

  return {
    axis,
    timeToX,
    xToLogical,
    priceToY,
    yToPrice,
    toPixel(anchor) {
      const x = timeToX(anchor.time)
      const y = priceToY(anchor.price)
      return x == null || y == null ? null : { x, y }
    },
    toAnchor(point, snapToBar) {
      const logical = xToLogical(point.x)
      const time = logicalToTime(snapToBar ? Math.round(logical) : logical, axis)
      const price = yToPrice(point.y)
      return time == null || price == null ? null : { time, price }
    },
  }
}
