import { timeToLogical, type TimeAxis } from './anchors'
import { formatChartPrice, formatDuration } from './format'
import type { Anchor } from './types'

export interface Measurement {
  priceChange: number
  /** The change as a percentage of the starting price. */
  percent: number
  bars: number
  seconds: number
}

/** What the ruler reports between two anchors. Never stored. */
export function measure(from: Anchor, to: Anchor, axis: TimeAxis): Measurement {
  const start = timeToLogical(from.time, axis)
  const end = timeToLogical(to.time, axis)
  return {
    priceChange: to.price - from.price,
    percent: from.price ? ((to.price - from.price) / from.price) * 100 : 0,
    bars: start == null || end == null ? 0 : Math.round(end - start),
    seconds: Math.round(to.time - from.time),
  }
}

/** The ruler's two lines: the price change with its percentage, then bars and time. */
export function describeMeasurement(m: Measurement): [string, string] {
  const priceSign = m.priceChange < 0 ? '-' : '+'
  const percentSign = m.percent < 0 ? '-' : '+'
  const bars = Math.abs(m.bars) === 1 ? 'bar' : 'bars'
  return [
    `${priceSign}${formatChartPrice(Math.abs(m.priceChange))} (${percentSign}${Math.abs(m.percent).toFixed(2)}%)`,
    `${m.bars} ${bars}, ${formatDuration(m.seconds)}`,
  ]
}
