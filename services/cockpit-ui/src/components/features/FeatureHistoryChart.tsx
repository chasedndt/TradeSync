import { useEffect, useRef } from 'react'
import { ColorType, LineStyle, createChart, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts'
import type { Candle, RegimeLabFeatureResult } from '../../api/types'
import type { FeatureDrawing } from './featureDrawing'

interface Props {
  feature: RegimeLabFeatureResult
  drawing: FeatureDrawing
  points: [number, number][]
  candles: Candle[]
}

/**
 * One feature's last seven days on the right scale, price on the left, the
 * normal band from the Regime Lab normalisation, a zero line where the sign
 * carries the meaning, and the current score marked at the latest reading.
 */
export function FeatureHistoryChart({ feature, drawing, points, candles }: Props) {
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const chart = createChart(el, {
      height: 220,
      width: el.clientWidth,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#8397aa', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' },
      grid: { vertLines: { color: 'rgba(131,151,170,0.08)' }, horzLines: { color: 'rgba(131,151,170,0.08)' } },
      leftPriceScale: { visible: true, borderColor: 'rgba(131,151,170,0.25)' },
      rightPriceScale: { borderColor: 'rgba(131,151,170,0.25)', minimumWidth: 72 },
      timeScale: { borderColor: 'rgba(131,151,170,0.25)', timeVisible: true },
      crosshair: { mode: 0 },
    })

    const first = points.length ? points[0][0] : 0
    const price = chart.addLineSeries({ priceScaleId: 'left', color: 'rgba(131,151,170,0.55)', lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
    price.setData(candles.filter((c) => c.time >= first).map((c) => ({ time: c.time as UTCTimestamp, value: c.close })))

    const data = points.map(([t, v]) => ({ time: t as UTCTimestamp, value: v }))
    let series: ISeriesApi<'Histogram'> | ISeriesApi<'Line'>
    if (drawing.kind === 'histogram') {
      const bars = chart.addHistogramSeries({ priceScaleId: 'right', priceLineVisible: false, lastValueVisible: true })
      bars.setData(data.map((d) => ({ ...d, color: d.value >= 0 ? 'rgba(63,178,127,0.75)' : 'rgba(224,87,74,0.75)' })))
      series = bars
    } else {
      const line = chart.addLineSeries({ priceScaleId: 'right', color: '#5ba9ff', lineWidth: 2, priceLineVisible: false, lastValueVisible: true })
      line.setData(data)
      series = line
    }

    const norm = feature.normalization
    if (norm && Number.isFinite(norm.center) && Number.isFinite(norm.dispersion) && norm.dispersion > 0) {
      series.createPriceLine({ price: norm.center, color: 'rgba(215,227,240,0.45)', lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: false, title: 'centre' })
      series.createPriceLine({ price: norm.center + 2 * norm.dispersion, color: 'rgba(227,178,60,0.6)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: '+2 spreads' })
      series.createPriceLine({ price: norm.center - 2 * norm.dispersion, color: 'rgba(227,178,60,0.6)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: '−2 spreads' })
    }
    if (drawing.zeroLine) {
      series.createPriceLine({ price: 0, color: 'rgba(131,151,170,0.5)', lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: '' })
    }

    const last = data[data.length - 1]
    if (last && feature.score != null && Math.abs(feature.score) >= 0.05) {
      const up = feature.score > 0
      series.setMarkers([{ time: last.time, position: up ? 'belowBar' : 'aboveBar', shape: up ? 'arrowUp' : 'arrowDown',
        color: up ? '#3fb27f' : '#e0574a', text: `score ${up ? '+' : ''}${feature.score.toFixed(2)}` }])
    }

    chart.timeScale().fitContent()
    const resize = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }))
    resize.observe(el)
    return () => { resize.disconnect(); chart.remove() }
  }, [feature, drawing, points, candles])

  return <div ref={ref} />
}
