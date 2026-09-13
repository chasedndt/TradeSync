import { useEffect, useRef } from 'react'
import { ColorType, LineStyle, createChart, type DeepPartial, type IChartApi, type LineWidth, type TimeChartOptions, type UTCTimestamp } from 'lightweight-charts'
import type { ChartSeries, HorizonChartPayload } from '../../api/horizonTypes'
import styles from './FeatureCard.module.css'

interface Stroke { color: string; width: LineWidth; style: LineStyle }

export const ROLE_STROKE: Record<string, Stroke> = {
  average: { color: '#5ba9ff', width: 2, style: LineStyle.Solid },
  momentum: { color: '#c792ea', width: 3, style: LineStyle.Solid },
  band_upper: { color: '#e3b23c', width: 1, style: LineStyle.Dashed },
  band_lower: { color: '#e3b23c', width: 1, style: LineStyle.Dashed },
  range_high: { color: '#e0574a', width: 1, style: LineStyle.Dotted },
  range_low: { color: '#3fb27f', width: 1, style: LineStyle.Dotted },
  oscillator: { color: '#5ba9ff', width: 2, style: LineStyle.Solid },
  feature: { color: '#8fb3d9', width: 2, style: LineStyle.Solid },
}

export const CONE_STROKE: Record<string, Stroke> = {
  median_pct: { color: '#d7e3f0', width: 2, style: LineStyle.Solid },
  p25_pct: { color: '#8397aa', width: 1, style: LineStyle.Dashed },
  p75_pct: { color: '#8397aa', width: 1, style: LineStyle.Dashed },
  p10_pct: { color: 'rgba(131,151,170,0.55)', width: 1, style: LineStyle.Dotted },
  p90_pct: { color: 'rgba(131,151,170,0.55)', width: 1, style: LineStyle.Dotted },
}

const options = (height: number, width: number): DeepPartial<TimeChartOptions> => ({
  height,
  width,
  layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#8397aa', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' },
  grid: { vertLines: { color: 'rgba(131,151,170,0.08)' }, horzLines: { color: 'rgba(131,151,170,0.08)' } },
  rightPriceScale: { borderColor: 'rgba(131,151,170,0.25)', minimumWidth: 72 },
  timeScale: { borderColor: 'rgba(131,151,170,0.25)' },
  crosshair: { mode: 0 },
})

const points = (series: [number, number][]) => series.map(([t, v]) => ({ time: t as UTCTimestamp, value: v }))

function addLine(chart: IChartApi, stroke: Stroke) {
  return chart.addLineSeries({ color: stroke.color, lineWidth: stroke.width, lineStyle: stroke.style, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
}

/**
 * Daily candles with one feature drawn the way it reads (an average, a band, a
 * range, the momentum leg), the record's cone forward from the last close, and
 * a lower pane for features read on their own scale (RSI, volume).
 */
export function FeatureChart({ payload, featureKey }: { payload: HorizonChartPayload; featureKey: string }) {
  const mainRef = useRef<HTMLDivElement | null>(null)
  const lowerRef = useRef<HTMLDivElement | null>(null)
  const overlays: ChartSeries[] = payload.overlays[featureKey] ?? []
  const hasLower = overlays.some((o) => o.pane === 'lower')

  useEffect(() => {
    const el = mainRef.current
    if (!el) return
    const chart = createChart(el, options(240, el.clientWidth))
    chart.addCandlestickSeries({ upColor: '#3fb27f', downColor: '#e0574a', borderUpColor: '#3fb27f', borderDownColor: '#e0574a', wickUpColor: '#3fb27f', wickDownColor: '#e0574a' })
      .setData(payload.candles.map((c) => ({ time: c.time as UTCTimestamp, open: c.open, high: c.high, low: c.low, close: c.close })))
    for (const overlay of overlays.filter((o) => o.pane === 'price')) {
      addLine(chart, ROLE_STROKE[overlay.role] ?? ROLE_STROKE.feature).setData(points(overlay.points))
    }
    for (const line of payload.projection.lines) {
      addLine(chart, CONE_STROKE[line.quantile]).setData(points(line.points))
    }
    chart.timeScale().fitContent()

    let lower: IChartApi | null = null
    if (hasLower && lowerRef.current) {
      lower = createChart(lowerRef.current, options(96, el.clientWidth))
      for (const overlay of overlays.filter((o) => o.pane === 'lower')) {
        if (overlay.kind === 'histogram') {
          lower.addHistogramSeries({ color: 'rgba(131,151,170,0.45)', priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false })
            .setData(points(overlay.points))
        } else {
          const series = addLine(lower, ROLE_STROKE[overlay.role] ?? ROLE_STROKE.feature)
          series.setData(points(overlay.points))
          for (const guide of overlay.guides ?? []) {
            series.createPriceLine({ price: guide, color: 'rgba(227,178,60,0.6)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: '' })
          }
        }
      }
      lower.timeScale().fitContent()
      const follower = lower
      chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
        if (!range) return
        try { follower.timeScale().setVisibleRange(range) } catch { /* the cone runs past the pane's data */ }
      })
    }

    const resize = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth })
      lower?.applyOptions({ width: el.clientWidth })
    })
    resize.observe(el)
    return () => {
      resize.disconnect()
      chart.remove()
      lower?.remove()
    }
  }, [payload, featureKey, overlays, hasLower])

  return (
    <div className={styles.chart}>
      <div ref={mainRef} />
      {hasLower && <div ref={lowerRef} className={styles.lower} />}
      <div className={styles.legend}>
        {overlays.map((o) => {
          const stroke = ROLE_STROKE[o.role] ?? ROLE_STROKE.feature
          return <span key={o.label}><i style={{ background: o.kind === 'histogram' ? 'rgba(131,151,170,0.45)' : stroke.color }} />{o.label}</span>
        })}
        {payload.projection.lines.length > 0 && <span><i style={{ background: CONE_STROKE.median_pct.color }} />record cone: median, middle half, 10th to 90th</span>}
      </div>
    </div>
  )
}
