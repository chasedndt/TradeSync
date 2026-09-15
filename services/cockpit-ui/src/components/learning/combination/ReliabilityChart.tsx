import { useState } from 'react'
import type { ForecastScore, ReliabilityBin } from '../../../api/evidenceCombinationTypes'
import { chartSize, plotPoint, probabilityPct } from './combinationFormat'
import { useElementWidth } from './useElementWidth'
import styles from './ReliabilityChart.module.css'

const LEFT = 38
const TOP = 8
const RIGHT = 10
const AXIS = 22
const TICKS = [0, 0.25, 0.5, 0.75, 1]

type SeriesKey = 'base' | 'combined'

interface Series {
  key: SeriesKey
  label: string
  bins: ReliabilityBin[]
}

const DOT: Record<SeriesKey, string> = { base: styles.ringBase, combined: styles.dotCombined }
const RADIUS: Record<SeriesKey, number> = { base: 5, combined: 4 }
const WHISKER: Record<SeriesKey, string> = { base: styles.whiskerBase, combined: styles.whiskerCombined }
const KEY: Record<SeriesKey, string> = { base: styles.keyBase, combined: styles.keyCombined }

const describe = (series: Series, bin: ReliabilityBin): string =>
  `${series.label}: forecast ${probabilityPct(bin.mean_probability)}, ${probabilityPct(bin.rise_share)} rose` +
  `${bin.low != null && bin.high != null ? ` (95% interval ${probabilityPct(bin.low)} to ${probabilityPct(bin.high)})` : ''}` +
  `, ${bin.decisions.toLocaleString()} decisions, ${bin.effective_windows.toFixed(1)} effective windows`

/**
 * Reliability: each bin's mean forecast (across) against the share that rose
 * (up), with its 95% interval at the bin's effective windows. On the diagonal
 * is calibrated. The base rate, one reference point, is drawn last as a ring so
 * it stays visible where combined sources' dots sit on top of it: shape as well
 * as colour tells them apart. Blue and amber are the Cockpit's chart pair,
 * validated for colour-vision deficiency on the panel surface; every value is
 * also in the table view.
 */
export function ReliabilityChart({ combined, baseRate, label }: { combined: ForecastScore; baseRate: ForecastScore; label: string }) {
  const [ref, width] = useElementWidth<HTMLElement>()
  const [active, setActive] = useState<string | null>(null)
  const series: Series[] = [
    { key: 'combined', label: 'Combined sources', bins: combined.bins },
    { key: 'base', label: 'Base rate', bins: baseRate.bins },
  ]
  const size = chartSize(width - LEFT - RIGHT)
  const frame = { left: LEFT, top: TOP, size }
  const svgWidth = LEFT + size + RIGHT
  const svgHeight = TOP + size + AXIS
  const at = (value: number) => TOP + (1 - value) * size
  const current = series.flatMap((s) => s.bins.map((bin, index) => ({ id: `${s.key}-${index}`, s, bin }))).find((item) => item.id === active)

  return (
    <figure className={styles.wrap} ref={ref}>
      <figcaption className={styles.caption}>Reliability of the forecasts · {label}</figcaption>
      <div className={styles.readout} aria-live="polite">
        {current ? (
          <>
            <strong className={styles.value}>{probabilityPct(current.bin.rise_share)} rose</strong>
            <span>{describe(current.s, current.bin).split(': ')[1]}</span>
          </>
        ) : (
          <span className={styles.hint}>Forecast across, share that rose up; the diagonal is perfect calibration. Hover or focus a dot.</span>
        )}
      </div>
      {width > 0 && (
        <svg className={styles.svg} width={svgWidth} height={svgHeight} viewBox={`0 0 ${svgWidth} ${svgHeight}`} role="img" aria-label={`Reliability of combined sources and the base rate, ${label}`}>
          {TICKS.map((tick) => (
            <g key={tick}>
              <line className={styles.grid} x1={LEFT} x2={LEFT + size} y1={at(tick)} y2={at(tick)} />
              <line className={styles.grid} x1={LEFT + tick * size} x2={LEFT + tick * size} y1={TOP} y2={TOP + size} />
              {tick % 0.5 === 0 && (
                <>
                  <text className={styles.tick} x={LEFT - 6} y={at(tick) + 3} textAnchor="end">{probabilityPct(tick, 0)}</text>
                  <text className={styles.tick} x={LEFT + tick * size} y={TOP + size + 14} textAnchor="middle">{probabilityPct(tick, 0)}</text>
                </>
              )}
            </g>
          ))}
          <line className={styles.diagonal} x1={LEFT} y1={TOP + size} x2={LEFT + size} y2={TOP} />
          {series.map((s) =>
            s.bins.map((bin, index) => {
              const id = `${s.key}-${index}`
              const point = plotPoint(bin, frame)
              return (
                <g key={id}>
                  {point.low != null && point.high != null && (
                    <line className={WHISKER[s.key]} x1={point.cx} x2={point.cx} y1={point.low} y2={point.high} />
                  )}
                  <circle className={`${DOT[s.key]} ${active === id ? styles.active : ''}`} cx={point.cx} cy={point.cy} r={RADIUS[s.key]} />
                  <circle
                    className={styles.hit}
                    cx={point.cx}
                    cy={point.cy}
                    r={12}
                    tabIndex={0}
                    role="img"
                    aria-label={describe(s, bin)}
                    onPointerEnter={() => setActive(id)}
                    onPointerLeave={() => setActive(null)}
                    onFocus={() => setActive(id)}
                    onBlur={() => setActive(null)}
                  />
                </g>
              )
            }),
          )}
        </svg>
      )}
      <ul className={styles.legend} aria-label="Series">
        {series.map((s) => (
          <li key={s.key}><span className={`${styles.key} ${KEY[s.key]}`} aria-hidden="true" />{s.label}</li>
        ))}
      </ul>
      <details className={styles.table}>
        <summary>Show as table</summary>
        <table>
          <thead><tr><th scope="col">Forecast</th><th scope="col">Mean forecast</th><th scope="col">Rose</th><th scope="col">95% interval</th><th scope="col">Decisions</th><th scope="col">Effective windows</th></tr></thead>
          <tbody>
            {series.flatMap((s) =>
              s.bins.map((bin, index) => (
                <tr key={`${s.key}-${index}`}>
                  <td>{s.label}</td>
                  <td>{probabilityPct(bin.mean_probability)}</td>
                  <td>{probabilityPct(bin.rise_share)}</td>
                  <td>{bin.low != null && bin.high != null ? `${probabilityPct(bin.low)} to ${probabilityPct(bin.high)}` : '—'}</td>
                  <td>{bin.decisions.toLocaleString()}</td>
                  <td>{bin.effective_windows.toFixed(1)}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </details>
    </figure>
  )
}
