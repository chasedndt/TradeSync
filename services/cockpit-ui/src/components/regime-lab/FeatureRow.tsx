import type { KeyboardEvent } from 'react'
import type { EvidenceCard } from '../../api/outcomeEvidenceTypes'
import type { RegimeLabFeatureResult } from '../../api/regimeLabTypes'
import { FeatureChartRow } from '../features/FeatureChartRow'
import { featureName } from '../features/featureDrawing'
import { cardCells, rowReason, type CardsState } from './featureReason'
import { REASON_LABELS, duration, reading, signed } from './format'
import styles from './FeatureTable.module.css'

interface Props {
  feature: RegimeLabFeatureResult
  symbol: string
  open: boolean
  onToggle: () => void
  card: EvidenceCard | undefined
  cardsState: CardsState
  columns: number
}

/** One feature's row in the evidence table; its seven-day chart opens beneath it. */
export function FeatureRow({ feature, symbol, open, onToggle, card, cardsState, columns }: Props) {
  const cells = cardCells(card, cardsState)
  const ageTone = feature.freshness === 'stale' ? styles.warn : feature.freshness === 'missing' ? styles.dim : ''
  const scoreTone = feature.score == null ? styles.dim : feature.score > 0 ? styles.good : feature.score < 0 ? styles.bad : ''
  const onKey = (event: KeyboardEvent<HTMLTableRowElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onToggle()
    }
  }

  return (
    <>
      <tr
        id={`feature-${feature.feature_id}`}
        className={`${styles.row} ${open ? styles.open : ''}`}
        tabIndex={0}
        aria-expanded={open}
        onClick={onToggle}
        onKeyDown={onKey}
        title={open ? 'Hide the chart' : 'Show seven days of readings'}
      >
        <td data-label="Feature">
          <span className={styles.name}>
            <span className={styles.caret} aria-hidden="true">{open ? '▾' : '▸'}</span>
            {featureName(feature.feature_id)}
          </span>
          <span className={styles.sub}>{feature.unit} · {feature.feed}</span>
        </td>
        <td data-label="Value" className={styles.num}>{reading(feature.current_value)}</td>
        <td data-label="Age" className={`${styles.num} ${ageTone}`}>{duration(feature.age_ms)}</td>
        <td data-label="History" className={styles.num}>
          {feature.minimum_history_points > 0 ? `${feature.history_count ?? 0}/${feature.minimum_history_points}` : '—'}
        </td>
        <td data-label="z" className={styles.num}>{signed(feature.normalization?.z_score)}</td>
        <td data-label="Score" className={`${styles.num} ${scoreTone}`}>{signed(feature.score, 3)}</td>
        <td data-label="Reason" className={styles.reasonCell}>
          <span className={styles.badge} data-reason={feature.coverage_reason}>{REASON_LABELS[feature.coverage_reason]}</span>
          <span className={styles.why}>{rowReason(feature)}</span>
        </td>
        <td data-label="Evidence card" className={styles[cells.tone]}>{cells.verdict}</td>
        <td data-label="Entries" className={styles.num}>{cells.entries}</td>
      </tr>
      {open && (
        <tr className={styles.chartRow}>
          <td colSpan={columns}>
            <FeatureChartRow feature={feature} symbol={symbol} />
          </td>
        </tr>
      )}
    </>
  )
}
