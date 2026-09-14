import { useRef, useState } from 'react'
import type { HorizonChartPayload } from '../../../api/horizonTypes'
import { INTERVAL_WORDS } from '../timeframeText'
import { ChartLegend } from './ChartLegend'
import { useHorizonCharts } from './useHorizonCharts'
import styles from './HorizonChart.module.css'

interface Props {
  payload?: HorizonChartPayload
  status: string | null
  horizonLabel: string
  labels: Record<string, string>
  active: Set<string>
  onToggle: (key: string) => void
}

/**
 * One large chart for the selected horizon: candles on the horizon's own bars,
 * the features chosen below drawn over them, the record's cone ahead, and a
 * titled lower pane for each feature read on its own scale. Panes scroll, zoom
 * and share a crosshair; the legend reads every value under it.
 */
export function HorizonChart({ payload, status, horizonLabel, labels, active, onToggle }: Props) {
  const [showCone, setShowCone] = useState(true)
  const [hover, setHover] = useState<number | null>(null)
  const mainRef = useRef<HTMLDivElement>(null)
  const lowerRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const keys = payload ? Object.keys(payload.overlays).filter((k) => payload.overlays[k].length) : []
  const lowerKeys = payload ? keys.filter((k) => active.has(k) && payload.overlays[k].some((o) => o.pane === 'lower')) : []
  const activeKey = keys.filter((k) => active.has(k)).join(',')
  const clearCrosshairs = useHorizonCharts({ payload, activeKey, showCone, lowerKeys, mainRef, lowerRefs, onHover: setHover })

  return (
    <section id="horizon-chart" className={`panel ${styles.panel}`} aria-labelledby="horizon-chart-title">
      <header className={styles.head}>
        <h3 id="horizon-chart-title">
          {horizonLabel} ahead{payload ? ` · ${INTERVAL_WORDS[payload.interval]} candles, last ${payload.candles.length}` : ''}
        </h3>
        <div className={styles.toggles} role="group" aria-label="Features on the chart">
          {keys.map((key) => (
            <button key={key} type="button" className={active.has(key) ? 'chip chip--active' : 'chip'} aria-pressed={active.has(key)} onClick={() => onToggle(key)}>
              {labels[key] ?? key}
            </button>
          ))}
          <button type="button" className={showCone ? 'chip chip--active' : 'chip'} aria-pressed={showCone} onClick={() => setShowCone((v) => !v)}>
            record cone
          </button>
        </div>
      </header>
      {payload ? (
        <div className={styles.panes} onMouseLeave={clearCrosshairs}>
          <ChartLegend payload={payload} active={active} showCone={showCone} time={hover} />
          <div ref={mainRef} className={styles.main} />
          {lowerKeys.map((key) => (
            <div key={key} className={styles.lowerWrap}>
              <span className={styles.paneTitle}>{labels[key] ?? key}</span>
              <div ref={(el) => { lowerRefs.current[key] = el }} className={styles.lower} />
            </div>
          ))}
          {showCone && payload.projection.note && <p className={styles.note}>{payload.projection.note}</p>}
        </div>
      ) : (
        <div className={styles.empty}>{status ?? 'Drawing the chart…'}</div>
      )}
    </section>
  )
}
