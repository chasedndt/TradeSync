import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type LogicalRange,
} from 'lightweight-charts'
import type { ContextPoint } from '../../api/types'

interface Props {
  /** Candle opens from the chart above. Defines this pane's time domain. */
  candleTimes: number[]
  points: ContextPoint[]
  colour: string
  /** Chart whose time scale this pane follows. */
  syncWith: IChartApi | null
  height?: number
  kind?: 'line' | 'histogram'
  /** Axis label formatter, e.g. basis points or millions of dollars. */
  format?: (value: number) => string
  /** Rendered where a value is drawn as a positive/negative bar. */
  baseline?: number
}

/**
 * One context series drawn beneath the price chart.
 *
 * The pane is given the candle times from the chart above and emits a slot for
 * every one of them, leaving the slot empty where there is no sample. That does
 * two things at once: the two charts share an identical logical index so the
 * time scales can be synced by index, and a collection gap renders as a gap
 * rather than as a line drawn straight through it.
 */
export function ContextPane({
  candleTimes,
  points,
  colour,
  syncWith,
  height = 96,
  kind = 'line',
  format,
  baseline = 0,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | ISeriesApi<'Histogram'> | null>(null)
  const formatRef = useRef(format)
  formatRef.current = format

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = createChart(el, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#8397aa',
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        fontSize: 10,
      },
      grid: {
        vertLines: { color: 'rgba(131,151,170,0.06)' },
        horzLines: { color: 'rgba(131,151,170,0.06)' },
      },
      // Same pinned width as the price chart, so the plot areas line up.
      rightPriceScale: {
        borderColor: 'rgba(131,151,170,0.20)',
        minimumWidth: 100,
      },
      // The time axis is the price chart's; repeating it under every pane
      // wastes vertical space and invites reading two axes as different.
      timeScale: { visible: false, borderVisible: false },
      crosshair: { mode: 0 },
      handleScroll: false,
      handleScale: false,
      localization: {
        priceFormatter: (value: number) =>
          formatRef.current ? formatRef.current(value) : String(value),
      },
    })

    seriesRef.current =
      kind === 'histogram'
        ? chart.addHistogramSeries({ color: colour, base: baseline })
        : chart.addLineSeries({ color: colour, lineWidth: 2, priceLineVisible: false })

    chartRef.current = chart

    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width
      if (width) chart.applyOptions({ width })
    })
    observer.observe(el)

    return () => {
      observer.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [height, kind, colour, baseline])

  useEffect(() => {
    const series = seriesRef.current
    if (!series) return

    const byTime = new Map(points.map((point) => [point.time, point.value]))
    series.setData(
      candleTimes.map((time) => {
        const value = byTime.get(time)
        // A slot with no sample is whitespace: it holds the index so the panes
        // stay aligned, and draws nothing.
        return value === undefined
          ? ({ time: time as never } as never)
          : ({ time: time as never, value } as never)
      }),
    )
  }, [candleTimes, points])

  // Follow the price chart by logical index. Both charts carry one slot per
  // candle, so index n means the same candle in each.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !syncWith) return

    const apply = (range: LogicalRange | null) => {
      if (range) chart.timeScale().setVisibleLogicalRange(range)
    }
    apply(syncWith.timeScale().getVisibleLogicalRange())
    syncWith.timeScale().subscribeVisibleLogicalRangeChange(apply)
    return () => syncWith.timeScale().unsubscribeVisibleLogicalRangeChange(apply)
  }, [syncWith, candleTimes])

  return <div ref={containerRef} style={{ width: '100%' }} />
}
