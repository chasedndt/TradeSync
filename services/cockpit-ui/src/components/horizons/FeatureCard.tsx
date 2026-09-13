import type { FeatureEvaluation, HorizonChartPayload } from '../../api/horizonTypes'
import { FeatureChart } from './FeatureChart'
import { LEAN_LABEL, recordLine } from './horizonText'
import styles from './FeatureCard.module.css'

interface Props {
  feature: FeatureEvaluation
  horizonLabel: string
  chart?: HorizonChartPayload
  chartState: 'loading' | 'error' | 'ready'
  highlighted: boolean
}

/** One feature at the selected horizon: what it reads today, what followed days like today, and the chart that shows it. */
export function FeatureCard({ feature, horizonLabel, chart, chartState, highlighted }: Props) {
  return (
    <article id={`feature-${feature.key}`} className={`panel ${styles.card} ${highlighted ? styles.flash : ''}`}>
      <header className={styles.head}>
        <h4>{feature.label}</h4>
        <span className={styles.kind}>{feature.kind === 'directional' ? 'direction' : 'context'}</span>
        <span className={`${styles.lean} ${styles[feature.record_lean]}`}>{LEAN_LABEL[feature.record_lean]}</span>
      </header>
      <p className={styles.reading}>{feature.text}</p>
      <p className={styles.record}>{recordLine(feature.record, horizonLabel)}</p>
      {chart ? (
        <FeatureChart payload={chart} featureKey={feature.key} />
      ) : (
        <div className={styles.empty}>{chartState === 'error' ? 'Chart unavailable from the state API.' : 'Drawing the chart…'}</div>
      )}
      <p className={styles.measures}>{feature.measures}</p>
    </article>
  )
}
