import { useEffect, useRef, useState } from 'react'
import { createChart, type IChartApi, type ISeriesApi } from 'lightweight-charts'
import type { Candle } from '../../api/types'
import type { ChartHandles, EvidenceMarker, PriceLevel } from './chartTypes'
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
  /** Horizontal price lines derived from venue data, such as resting walls. */
  levels?: PriceLevel[]
  height?: number
  /**
   * Handed the chart and its candle series once they exist, so a drawing layer
   * can attach and panes below can follow the time scale. Called with null on
   * unmount.
   */
  onReady?: (handles: ChartHandles | null) => void
}

/**
 * Hyperliquid price with paper-evidence markers.
 *
 * The chart owns no data fetching and no interpretation: it draws exactly what
 * it is given. Markers are placed from recorded paper signals, so a mark on
 * this chart always corresponds to a stored row that can be inspected.
 *
 * Drawing is not part of the chart. The Market Canvas attaches its drawing
 * layer through `onReady`; a chart used without it, as on the home page, has
 * no drawing at all.
 */
export function PriceChart({ candles, markers = [], levels = [], height = 460, onReady }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const fittedRef = useRef(false)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  // Kept in a ref so the chart, created once, always reports to the current callback.
  const onReadyRef = useRef(onReady)
  onReadyRef.current = onReady
  const [seriesApi, setSeriesApi] = useState<ISeriesApi<'Candlestick'> | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    fittedRef.current = false

    const chart = createChart(el, priceChartOptions(height))
    const series = chart.addCandlestickSeries(CANDLE_SERIES_OPTIONS)
    const volume = chart.addHistogramSeries(VOLUME_SERIES_OPTIONS)
    chart.priceScale('volume').applyOptions({
      scaleMargins: VOLUME_SCALE_MARGINS,
    })

    chartRef.current = chart
    seriesRef.current = series
    volumeRef.current = volume
    setSeriesApi(series)
    onReadyRef.current?.({ chart, series })

    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width
      if (width) chart.applyOptions({ width })
    })
    observer.observe(el)

    return () => {
      observer.disconnect()
      onReadyRef.current?.(null)
      chart.remove()
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
  }, [candles])

  usePriceLines(seriesApi, levels)
  useSeriesMarkers(seriesApi, markers)

  return <div ref={containerRef} style={{ width: '100%' }} />
}
