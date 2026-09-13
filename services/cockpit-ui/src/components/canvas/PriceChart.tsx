import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  ColorType,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
} from 'lightweight-charts'
import type { Candle } from '../../api/types'
import { DrawingOverlay, type Shape } from './DrawingOverlay'

export interface EvidenceMarker {
  /** UNIX seconds, aligned to a candle open. */
  time: number
  direction: 'LONG' | 'SHORT' | 'NONE'
  label: string
  /** A change of side is drawn as a labelled arrow; a held side as a small unlabelled dot. */
  kind?: 'change' | 'continuation'
}

export interface PriceLevel {
  drawingId: string
  price: number
  label: string
  colour?: string
  /**
   * Dashed is an operator annotation; dotted is derived from venue data and is
   * not something the operator drew. Keeping them visually distinct matters —
   * a resting wall disappears the moment the order is pulled, while a level the
   * operator placed is theirs until they remove it.
   */
  style?: 'dashed' | 'dotted'
}

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
  const priceLinesRef = useRef<Map<string, IPriceLine>>(new Map())
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

    const chart = createChart(el, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#8397aa',
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      },
      grid: {
        vertLines: { color: 'rgba(131,151,170,0.10)' },
        horzLines: { color: 'rgba(131,151,170,0.10)' },
      },
      // Pinned width shared with the context panes below, so their plot areas
      // start at the same x and a funding spike lines up with its candle.
      rightPriceScale: { borderColor: 'rgba(131,151,170,0.25)', minimumWidth: 100 },
      timeScale: { borderColor: 'rgba(131,151,170,0.25)', timeVisible: true },
      crosshair: { mode: 0 },
    })

    seriesRef.current = chart.addCandlestickSeries({
      upColor: '#3fb27f',
      downColor: '#e0574a',
      borderUpColor: '#3fb27f',
      borderDownColor: '#e0574a',
      wickUpColor: '#3fb27f',
      wickDownColor: '#e0574a',
    })

    setSeriesApi(seriesRef.current)

    volumeRef.current = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
      color: 'rgba(131,151,170,0.35)',
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
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
      priceLinesRef.current.clear()
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

  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    const existing = priceLinesRef.current
    const wanted = new Set(levels.map((l) => l.drawingId))

    // Remove lines whose drawing is gone, so a deleted level leaves the chart.
    for (const [id, line] of existing) {
      if (!wanted.has(id)) {
        series.removePriceLine(line)
        existing.delete(id)
      }
    }
    // Recreate changed ones: the library has no update for a price line.
    for (const level of levels) {
      const previous = existing.get(level.drawingId)
      if (previous) series.removePriceLine(previous)
      existing.set(
        level.drawingId,
        series.createPriceLine({
          price: level.price,
          color: level.colour || '#e3b23c',
          lineWidth: 1,
          lineStyle: level.style === 'dotted' ? LineStyle.Dotted : LineStyle.Dashed,
          axisLabelVisible: true,
          title: level.label || '',
        }),
      )
    }
  }, [levels])

  useEffect(() => {
    if (!seriesRef.current) return
    seriesRef.current.setMarkers(
      markers.map((m) => {
        const change = m.kind !== 'continuation'
        const short = m.direction === 'SHORT'
        return {
          time: m.time as never,
          position: short ? 'aboveBar' : 'belowBar',
          color: short ? (change ? '#e0574a' : 'rgba(224,87,74,0.55)') : (change ? '#3fb27f' : 'rgba(63,178,127,0.55)'),
          shape: change ? (short ? 'arrowDown' : 'arrowUp') : 'circle',
          size: change ? 1 : 0.35,
          text: change ? m.label : '',
        }
      }),
    )
  }, [markers])

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
