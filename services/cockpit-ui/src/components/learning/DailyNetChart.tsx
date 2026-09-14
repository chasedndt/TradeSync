import { useEffect, useRef, useState } from 'react'
import type { DailyScore } from '../../api/learningTypes'
import { columnPath, niceCeiling } from './chartGeometry'
import { sharePct, signedPct } from './format'
import styles from './DailyNetChart.module.css'

const TOP = 8
const PLOT = 110
const AXIS = 20
const LEFT = 54
const RIGHT = 6
const HEIGHT = TOP + PLOT + AXIS

function useWidth() {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const update = () => setWidth(element.clientWidth)
    update()
    const observer = new ResizeObserver(update)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}

/**
 * Mean net return per UTC day, as columns above or below zero: blue above,
 * amber below (a pair validated for colour-vision deficiency on this surface).
 * Position carries the sign too, and every value is in the table view.
 */
export function DailyNetChart({ daily, label }: { daily: DailyScore[]; label: string }) {
  const [ref, width] = useWidth()
  const [active, setActive] = useState<number | null>(null)
  const measured = daily.some((day) => day.mean_net_return_pct != null)

  const top = niceCeiling(Math.max(0, ...daily.map((day) => Math.abs(day.mean_net_return_pct ?? 0))))
  const band = daily.length ? Math.max(0, width - LEFT - RIGHT) / daily.length : 0
  const barWidth = Math.max(2, Math.min(24, band * 0.6))
  const y = (value: number) => TOP + (PLOT / 2) * (1 - value / top)
  const zero = y(0)
  const current = active == null ? null : daily[active]

  return (
    <div className={styles.wrap} ref={ref}>
      <div className={styles.readout} aria-live="polite">
        {current ? (
          <>
            <strong className={styles.value}>{signedPct(current.mean_net_return_pct, 3)}</strong>
            <span>{current.day} · {current.attributions} calls · {sharePct(current.net_hit_rate)} won after costs</span>
          </>
        ) : (
          <span className={styles.hint}>Mean net return per day. Hover or focus a day for its values.</span>
        )}
      </div>
      {!measured ? (
        <p className={styles.empty}>No daily result yet.</p>
      ) : width > 0 && (
        <svg width={width} height={HEIGHT} role="img" aria-label={`${label}: mean net return per day`}>
          <line className={styles.grid} x1={LEFT} x2={width - RIGHT} y1={y(top)} y2={y(top)} />
          <line className={styles.grid} x1={LEFT} x2={width - RIGHT} y1={y(-top)} y2={y(-top)} />
          <line className={styles.baseline} x1={LEFT} x2={width - RIGHT} y1={zero} y2={zero} />
          <text className={styles.tick} x={LEFT - 6} y={y(top) + 3} textAnchor="end">{signedPct(top)}</text>
          <text className={styles.tick} x={LEFT - 6} y={zero + 3} textAnchor="end">0%</text>
          <text className={styles.tick} x={LEFT - 6} y={y(-top) + 3} textAnchor="end">{signedPct(-top)}</text>
          {daily.map((day, index) => {
            const x = LEFT + index * band
            const value = day.mean_net_return_pct
            return (
              <g key={day.day}>
                {value != null && (
                  <path
                    className={`${value >= 0 ? styles.up : styles.down} ${active === index ? styles.active : ''}`}
                    d={columnPath(x + (band - barWidth) / 2, barWidth, zero, y(value))}
                  />
                )}
                <rect
                  className={styles.hit}
                  x={x}
                  y={TOP}
                  width={band}
                  height={PLOT}
                  tabIndex={0}
                  role="img"
                  aria-label={`${day.day}: ${value == null ? 'no result' : `${signedPct(value, 3)} mean net`}, ${day.attributions} calls`}
                  onPointerEnter={() => setActive(index)}
                  onPointerLeave={() => setActive(null)}
                  onFocus={() => setActive(index)}
                  onBlur={() => setActive(null)}
                />
              </g>
            )
          })}
          <text className={styles.tick} x={LEFT} y={HEIGHT - 5}>{daily[0].day.slice(5)}</text>
          <text className={styles.tick} x={width - RIGHT} y={HEIGHT - 5} textAnchor="end">{daily[daily.length - 1].day.slice(5)}</text>
        </svg>
      )}
      {daily.length > 0 && (
        <details className={styles.table}>
          <summary>Show as table</summary>
          <table>
            <thead><tr><th scope="col">Day (UTC)</th><th scope="col">Calls</th><th scope="col">Won after costs</th><th scope="col">Mean net</th></tr></thead>
            <tbody>
              {daily.map((day) => (
                <tr key={day.day}><td>{day.day}</td><td>{day.attributions}</td><td>{sharePct(day.net_hit_rate)}</td><td>{signedPct(day.mean_net_return_pct, 3)}</td></tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  )
}
