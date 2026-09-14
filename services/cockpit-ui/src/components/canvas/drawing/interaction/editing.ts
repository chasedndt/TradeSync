import { logicalToTime, timeToLogical, type TimeAxis } from '../anchors'
import type { Projection } from '../projection'
import { snapAngle } from '../snap'
import { ANGLE_SNAPPED } from '../tools'
import type { Anchor, ChartShape, HitPart, PixelPoint } from '../types'

/** Anchors moved together by whole bars and a price difference, or null if any would leave the chart. */
export function translateAnchors(
  anchors: readonly Anchor[],
  bars: number,
  priceDelta: number,
  axis: TimeAxis,
): Anchor[] | null {
  const moved: Anchor[] = []
  for (const anchor of anchors) {
    const logical = timeToLogical(anchor.time, axis)
    const time = logical == null ? null : logicalToTime(logical + bars, axis)
    const price = anchor.price + priceDelta
    if (time == null || !(price > 0)) return null
    moved.push({ time, price })
  }
  return moved
}

/**
 * A shape's anchors after dragging `part` from `from` to `to`.
 *
 * The body moves by whole bars, so anchors placed on candles stay on candles.
 * A handle moves one anchor to the bar under the pointer; with Shift, a line's
 * end snaps to 0, 45 or 90 degrees from its other end instead. A horizontal
 * line only ever moves in price and a vertical line only in time.
 */
export function draggedAnchors(
  shape: ChartShape,
  original: readonly Anchor[],
  part: HitPart,
  from: PixelPoint,
  to: PixelPoint,
  view: Projection,
  shift: boolean,
): Anchor[] | null {
  if (part.kind === 'body') {
    const startPrice = view.yToPrice(from.y)
    const endPrice = view.yToPrice(to.y)
    if (startPrice == null || endPrice == null) return null
    const bars = shape.kind === 'horizontal' ? 0 : Math.round(view.xToLogical(to.x) - view.xToLogical(from.x))
    const priceDelta = shape.kind === 'vertical' ? 0 : endPrice - startPrice
    return translateAnchors(original, bars, priceDelta, view.axis)
  }

  const current = original[part.index]
  if (!current) return null
  const snapping = shift && ANGLE_SNAPPED.has(shape.kind) && original.length === 2
  let target = to
  if (snapping) {
    const other = view.toPixel(original[1 - part.index])
    if (other) target = snapAngle(other, to)
  }
  const anchor = view.toAnchor(target, !snapping)
  if (!anchor || !(anchor.price > 0)) return null

  const next = [...original]
  next[part.index] =
    shape.kind === 'horizontal'
      ? { time: current.time, price: anchor.price }
      : shape.kind === 'vertical'
        ? { time: anchor.time, price: current.price }
        : anchor
  return next
}

export function sameAnchors(a: readonly Anchor[], b: readonly Anchor[]): boolean {
  return a.length === b.length && a.every((anchor, i) => anchor.time === b[i].time && anchor.price === b[i].price)
}
