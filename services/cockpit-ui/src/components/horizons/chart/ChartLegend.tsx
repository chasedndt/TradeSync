import type { HorizonChartPayload } from '../../../api/horizonTypes'
import { price } from '../../ledger/format'
import { CANDLE, CONE, VOLUME, strokeFor } from './chartStyles'
import { valueAt } from './valueAt'
import styles from './HorizonChart.module.css'

interface Props {
  payload: HorizonChartPayload
  active: Set<string>
  showCone: boolean
  time: number | null
}

const compact = (v: number) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}m` : Math.abs(v) >= 1e3 ? `${(v / 1e3).toFixed(1)}k` : v.toFixed(0))
const when = (t: number, intraday: boolean) =>
  new Date(t * 1000).toLocaleString(undefined, intraday ? { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' } : { day: 'numeric', month: 'short', year: 'numeric' })

/** What every line on the chart is, with its value under the crosshair (or at the last bar). */
export function ChartLegend({ payload, active, showCone, time }: Props) {
  const last = payload.candles[payload.candles.length - 1]
  const t = time ?? last?.time ?? 0
  const candle = payload.candles.find((c) => c.time === t) ?? (t > (last?.time ?? 0) ? undefined : last)
  const items: { key: string; label: string; color: string; dashed: boolean; value?: string }[] = []
  for (const key of Object.keys(payload.overlays)) {
    if (!active.has(key)) continue
    for (const overlay of payload.overlays[key]) {
      const stroke = strokeFor(key, overlay.role)
      const value = valueAt(overlay.points, t)
      const shown = value === undefined ? undefined : overlay.kind === 'histogram' ? compact(value) : overlay.range ? value.toFixed(0) : price(value)
      items.push({ key: `${key}-${overlay.label}`, label: overlay.label, color: overlay.kind === 'histogram' ? VOLUME : stroke.color, dashed: stroke.style !== 0, value: shown })
    }
  }
  const median = payload.projection.lines.find((l) => l.quantile === 'median_pct')
  return (
    <div className={styles.legend}>
      <span className={styles.when}>{t ? when(t, payload.interval !== '1d') : ''}</span>
      {candle && (
        <span className={styles.ohlc}>
          O {price(candle.open)} H {price(candle.high)} L {price(candle.low)}{' '}
          <b style={{ color: candle.close >= candle.open ? CANDLE.up : CANDLE.down }}>C {price(candle.close)}</b>
        </span>
      )}
      {items.map((item) => (
        <span key={item.key} className={styles.item}>
          <i style={{ borderTop: `2px ${item.dashed ? 'dashed' : 'solid'} ${item.color}` }} />{item.label}{item.value ? <b>{item.value}</b> : null}
        </span>
      ))}
      {showCone && median && (
        <span className={styles.item}>
          <i style={{ borderTop: `2px solid ${CONE.median_pct.color}` }} />record cone: median {price(median.points[median.points.length - 1]?.[1])}, middle half and 10th to 90th
        </span>
      )}
    </div>
  )
}
