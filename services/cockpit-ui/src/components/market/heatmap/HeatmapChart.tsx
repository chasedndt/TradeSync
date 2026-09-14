import { useEffect, useRef } from 'react'
import { ColorType, CrosshairMode, createChart, LineStyle, type IChartApi, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts'
import type { WindowCandle } from '../../../api/liquidityTypes'
import { HeatmapPrimitive, type HeatLayer } from './HeatmapPrimitive'
import styles from './HeatmapChart.module.css'

interface Props {
  candles: WindowCandle[]
  layer: HeatLayer | null
  intraday: boolean
  levels?: { price: number; colour: string; title: string }[]
  onHover?: (point: { time: number; price: number } | null) => void
}

/** Candles over a heatmap painted behind them, with optional marked levels; the heatmap follows every pan and zoom. */
export function HeatmapChart({ candles, layer, intraday, levels = [], onHover }: Props) {
  const el = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const primitiveRef = useRef<HeatmapPrimitive | null>(null)
  const hoverRef = useRef(onHover)
  hoverRef.current = onHover

  useEffect(() => {
    if (!el.current) return
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: '#0b0f17' }, textColor: '#8397aa', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' },
      grid: { vertLines: { color: 'rgba(131, 151, 170, 0.05)' }, horzLines: { color: 'rgba(131, 151, 170, 0.05)' } },
      rightPriceScale: { borderColor: 'rgba(131, 151, 170, 0.25)', minimumWidth: 76 },
      timeScale: { borderColor: 'rgba(131, 151, 170, 0.25)', timeVisible: intraday, secondsVisible: false, rightOffset: 3 },
      crosshair: { mode: CrosshairMode.Normal },
    })
    const series = chart.addCandlestickSeries({ upColor: '#e5e9f0', downColor: '#5e6b7a', borderUpColor: '#e5e9f0', borderDownColor: '#8397aa', wickUpColor: '#c0cad6', wickDownColor: '#8397aa' })
    const primitive = new HeatmapPrimitive()
    series.attachPrimitive(primitive)
    chart.subscribeCrosshairMove((param) => {
      const price = param.point ? series.coordinateToPrice(param.point.y) : null
      hoverRef.current?.(typeof param.time === 'number' && price !== null ? { time: param.time, price } : null)
    })
    chartRef.current = chart
    seriesRef.current = series
    primitiveRef.current = primitive
    return () => {
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
      primitiveRef.current = null
    }
  }, [intraday])

  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    series.setData(candles.map((c) => ({ time: c.time as UTCTimestamp, open: c.open, high: c.high, low: c.low, close: c.close })))
    chartRef.current?.timeScale().fitContent()
  }, [candles, intraday])

  useEffect(() => {
    primitiveRef.current?.setLayer(layer)
  }, [layer, intraday])

  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    const lines = levels.map((level) => series.createPriceLine({ price: level.price, color: level.colour, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: level.title }))
    return () => lines.forEach((line) => series.removePriceLine(line))
  }, [levels, intraday])

  return <div ref={el} className={styles.chart} />
}
