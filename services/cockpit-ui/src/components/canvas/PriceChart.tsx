import { useEffect, useRef, useState } from 'react'
import { createChart, type IChartApi, type ISeriesApi } from 'lightweight-charts'
import type { Candle } from '../../api/types'
import { DrawingOverlay, type Shape } from './DrawingOverlay'
import type { EvidenceMarker, PriceLevel } from './chartTypes'
import {
  CANDLE_SERIES_OPTIONS,
  priceChartOptions,
  VOLUME_SCALE_MARGINS,
  VOLUME_SERIES_OPTIONS,
} from './chartOptions'
import { usePriceLines } from './usePriceLines'
import { useSeriesMarkers } from './useSeriesMarkers'

interface Props {
  candles: Candle[]
  markers?: EvidenceMarker[]
  /** Operator levels, persisted and versioned server-side. */
  levels?: PriceLevel[]
  /** Two-anchor shapes, drawn in an overlay above the chart. */
  shapes?: Shape[]
  height?: number
  /** Called with the clicked price when the operator is placing a level. */
  onPickPrice?: (price: number) => void
  /** Called with time and price when placing a two-anchor shape. */
  onPickPoint?: (point: { time_s: number; price: number }) => void
  /**
   * Handed the chart api so panes below can follow this chart's time scale.
   * Called with null on unmount.
   */
  onChartReady?: (chart: IChartApi | null) => void
}

/**
 * Hyperliquid price with paper-evidence markers.
 *
 * The chart owns no data fetching and no interpretation: it draws exactly what
 * it is given. Markers are placed from recorded paper signals, so a mark on
 * this chart always corresponds to a stored row that can be inspected.
 */
export function PriceChart({
  candles,
  markers = [],
  levels = [],
  shapes = [],
  height = 460,
  onPickPrice,
  onPickPoint,
  onChartReady,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const fittedRef = useRef(false)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  // Kept in a ref so the chart's click handler, registered once, always
  // sees the current callback rather than the one from first render.
  const onPickPriceRef = useRef(onPickPrice)
  onPickPriceRef.current = onPickPrice
  const onPickPointRef = useRef(onPickPoint)
  onPickPointRef.current = onPickPoint
  const onChartReadyRef = useRef(onChartReady)
  onChartReadyRef.current = onChartReady
  // Bumped whenever data or size changes, so the overlay reprojects.
  const [revision, setRevision] = useState(0)
  const [chartApi, setChartApi] = useState<IChartApi | null>(null)
  const [seriesApi, setSeriesApi] = useState<ISeriesApi<'Candlestick'> | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    fittedRef.current = false

    const chart = createChart(el, priceChartOptions(height))

    seriesRef.current = chart.addCandlestickSeries(CANDLE_SERIES_OPTIONS)

    setSeriesApi(seriesRef.current)

    volumeRef.current = chart.addHistogramSeries(VOLUME_SERIES_OPTIONS)
    chart.priceScale('volume').applyOptions({
      scaleMargins: VOLUME_SCALE_MARGINS,
    })

    chartRef.current = chart

    chart.subscribeClick((param) => {
      const series = seriesRef.current
      if (!series || !param.point) return
      const price = series.coordinateToPrice(param.point.y)
      if (price == null) return

      const pointHandler = onPickPointRef.current
      if (pointHandler) {
        // param.time is absent when the click lands outside the plotted data;
        // falling back to now would anchor the shape where it was not placed.
        if (param.time == null) return
        pointHandler({ time_s: Number(param.time), price: Number(price) })
        return
      }
      onPickPriceRef.current?.(Number(price))
    })

    setChartApi(chart)
    onChartReadyRef.current?.(chart)

    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width
      if (width) chart.applyOptions({ width })
    })
    observer.observe(el)

    return () => {
      observer.disconnect()
      onChartReadyRef.current?.(null)
      chart.remove()
      setChartApi(null)
      setSeriesApi(null)
      chartRef.current = null
      seriesRef.current = null
      volumeRef.current = null
    }
  }, [height])

  useEffect(() => {
    if (!seriesRef.current || !volumeRef.current) return
    seriesRef.current.setData(
      candles.map((c) => ({
        time: c.time as never,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    )
    volumeRef.current.setData(
      candles.map((c) => ({
        time: c.time as never,
        value: c.volume,
        color: c.close >= c.open ? 'rgba(63,178,127,0.28)' : 'rgba(224,87,74,0.28)',
      })),
    )
    if (candles.length && chartRef.current && !fittedRef.current) {
      chartRef.current.timeScale().fitContent()
      fittedRef.current = true
    }
    setRevision((r) => r + 1)
  }, [candles])

  usePriceLines(seriesApi, levels)
  useSeriesMarkers(seriesApi, markers)

  return (
    <div ref={containerRef} style={{ width: '100%', position: 'relative' }}>
      <DrawingOverlay
        chart={chartApi}
        series={seriesApi}
        shapes={shapes}
        revision={revision}
      />
    </div>
  )
}
