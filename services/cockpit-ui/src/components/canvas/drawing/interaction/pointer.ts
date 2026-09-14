import type { IChartApi } from 'lightweight-charts'
import type { PixelPoint } from '../types'

export interface PanePoint extends PixelPoint {
  /** Whether the point is over the price pane, rather than an axis or outside the chart. */
  inside: boolean
}

/** Where a pointer event falls, in the price pane's own pixels. */
export function panePoint(event: PointerEvent, chart: IChartApi): PanePoint {
  const rect = chart.chartElement().getBoundingClientRect()
  // The pane starts after the left price scale, which is zero wide when hidden.
  const x = event.clientX - rect.left - chart.priceScale('left').width()
  const y = event.clientY - rect.top
  const { width, height } = chart.paneSize()
  return { x, y, inside: x >= 0 && y >= 0 && x <= width && y <= height }
}
