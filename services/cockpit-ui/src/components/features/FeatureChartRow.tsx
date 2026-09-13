import { useMemo } from 'react'
import { useCandles } from '../../api/hooks/useCandles'
import { useFeatureHistory } from '../../api/hooks/useFeatureHistory'
import type { RegimeLabFeatureResult } from '../../api/types'
import { FeatureHistoryChart } from './FeatureHistoryChart'
import { drawingFor, expectation } from './featureDrawing'
import styles from './FeatureChartRow.module.css'

/** The chart under a feature's row on Regime Lab: what it has read for seven days, and what today's reading says. */
export function FeatureChartRow({ feature, symbol }: { feature: RegimeLabFeatureResult; symbol: string }) {
  const history = useFeatureHistory(symbol, feature.feature_id, true)
  const candles = useCandles(symbol, '1h', 170)
  const drawing = useMemo(() => drawingFor(feature), [feature])
  const points = history.data?.series[feature.feature_id] ?? []

  return (
    <div className={styles.row}>
      <p className={styles.expect}>{expectation(feature)}</p>
      {history.isLoading ? (
        <div className={styles.empty}>Loading seven days of readings…</div>
      ) : history.isError ? (
        <div className={styles.empty}>Feature history unavailable: {(history.error as Error).message}</div>
      ) : points.length < 2 ? (
        <div className={styles.empty}>No recorded history for this feature in the last seven days.</div>
      ) : (
        <FeatureHistoryChart feature={feature} drawing={drawing} points={points} candles={candles.data?.candles ?? []} />
      )}
      <p className={styles.how}>{drawing.how} {points.length > 0 ? `${points.length} readings.` : ''}</p>
    </div>
  )
}
