import { useEffect, useRef, type MutableRefObject, type RefObject } from 'react'
import { createChart, type IChartApi, type ISeriesApi, type MouseEventParams, type SeriesType, type UTCTimestamp } from 'lightweight-charts'
import type { HorizonChartPayload } from '../../../api/horizonTypes'
import { CANDLE, CONE, GUIDE, VOLUME, chartOptions, strokeFor, type Stroke } from './chartStyles'
import { valueAt } from './valueAt'

interface Params {
  payload?: HorizonChartPayload
  activeKey: string
  showCone: boolean
  lowerKeys: string[]
  mainRef: RefObject<HTMLDivElement>
  lowerRefs: MutableRefObject<Record<string, HTMLDivElement | null>>
  onHover: (time: number | null) => void
}

interface Pane {
  chart: IChartApi
  series: ISeriesApi<SeriesType>
  points: [number, number][]
}

const asPoints = (series: [number, number][]) => series.map(([t, v]) => ({ time: t as UTCTimestamp, value: v }))

function addLine(chart: IChartApi, stroke: Stroke) {
  return chart.addLineSeries({ color: stroke.color, lineWidth: stroke.width, lineStyle: stroke.style, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
}

/**
 * Builds the price pane (candles, the chosen features' overlays and the record's
 * cone) and one lower pane per chosen feature read on its own scale (RSI,
 * volume). Every lower pane carries the price pane's time points, so the panes
 * scroll, zoom and share a crosshair point for point. Returns a function that
 * clears every crosshair, for when the pointer leaves the chart.
 */
export function useHorizonCharts({ payload, activeKey, showCone, lowerKeys, mainRef, lowerRefs, onHover }: Params) {
  const clear = useRef<() => void>(() => undefined)
  const lowerKey = lowerKeys.join(',')

  useEffect(() => {
    const mainEl = mainRef.current
    if (!payload || !mainEl) return
    const active = new Set(activeKey ? activeKey.split(',') : [])
    const timeVisible = payload.interval !== '1d'
    const main = createChart(mainEl, chartOptions(timeVisible, lowerKeys.length === 0))
    const candles = main.addCandlestickSeries({ upColor: CANDLE.up, downColor: CANDLE.down, borderUpColor: CANDLE.up, borderDownColor: CANDLE.down, wickUpColor: CANDLE.up, wickDownColor: CANDLE.down })
    candles.setData(payload.candles.map((c) => ({ time: c.time as UTCTimestamp, open: c.open, high: c.high, low: c.low, close: c.close })))
    for (const key of active) {
      for (const overlay of (payload.overlays[key] ?? []).filter((o) => o.pane === 'price')) addLine(main, strokeFor(key, overlay.role)).setData(asPoints(overlay.points))
    }
    const coneTimes: number[] = []
    if (showCone) {
      for (const line of payload.projection.lines) {
        addLine(main, CONE[line.quantile]).setData(asPoints(line.points))
        coneTimes.push(...line.points.map(([t]) => t))
      }
    }
    const times = [...new Set([...payload.candles.map((c) => c.time), ...coneTimes])].sort((a, b) => a - b)
    const panes: Pane[] = [{ chart: main, series: candles, points: payload.candles.map((c) => [c.time, c.close]) }]

    lowerKeys.forEach((key, index) => {
      const el = lowerRefs.current[key]
      const overlays = (payload.overlays[key] ?? []).filter((o) => o.pane === 'lower')
      if (!el || !overlays.length) return
      const chart = createChart(el, chartOptions(timeVisible, index === lowerKeys.length - 1))
      chart.addLineSeries({ visible: false }).setData(times.map((t) => ({ time: t as UTCTimestamp })))
      let first: Pane | null = null
      for (const overlay of overlays) {
        const series: ISeriesApi<SeriesType> = overlay.kind === 'histogram'
          ? chart.addHistogramSeries({ color: VOLUME, priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false })
          : addLine(chart, strokeFor(key, overlay.role))
        series.setData(asPoints(overlay.points))
        for (const guide of overlay.guides ?? []) series.createPriceLine({ price: guide, color: GUIDE, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '' })
        if (overlay.range) {
          const [minValue, maxValue] = overlay.range
          series.applyOptions({ autoscaleInfoProvider: () => ({ priceRange: { minValue, maxValue } }) })
        }
        first ??= { chart, series, points: overlay.points }
      }
      if (first) panes.push(first)
    })

    let syncing = false
    const rangeHandlers = panes.map(({ chart: source }) => {
      const handler = (range: { from: number; to: number } | null) => {
        if (syncing || !range) return
        syncing = true
        for (const { chart } of panes) if (chart !== source) chart.timeScale().setVisibleLogicalRange(range)
        syncing = false
      }
      source.timeScale().subscribeVisibleLogicalRangeChange(handler)
      return handler
    })
    const moveHandlers = panes.map((source, index) => {
      const handler = (param: MouseEventParams) => {
        if (!param.sourceEvent || typeof param.time !== 'number') return  // programmatic moves do not propagate
        const time = param.time
        onHover(time)
        panes.forEach((target, j) => {
          if (j === index) return
          const value = valueAt(target.points, time)
          if (value !== undefined) target.chart.setCrosshairPosition(value, time as UTCTimestamp, target.series)
        })
      }
      source.chart.subscribeCrosshairMove(handler)
      return handler
    })
    clear.current = () => {
      onHover(null)
      for (const { chart } of panes) chart.clearCrosshairPosition()
    }
    main.timeScale().fitContent()

    return () => {
      clear.current = () => undefined
      panes.forEach(({ chart }, i) => {
        chart.timeScale().unsubscribeVisibleLogicalRangeChange(rangeHandlers[i])
        chart.unsubscribeCrosshairMove(moveHandlers[i])
      })
      for (const { chart } of panes) chart.remove()
    }
    // lowerKeys is represented by lowerKey; onHover is a stable state setter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload, activeKey, showCone, lowerKey, mainRef, lowerRefs])

  return () => clear.current()
}
