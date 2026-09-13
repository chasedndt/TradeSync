import type { HorizonEvaluation, HorizonRead } from '../../api/horizonTypes'
import { price } from '../ledger/format'
import { LEAN_LABEL, TREND_WORDS, horizonAdjective, recordLine, signedPct } from './horizonText'
import { LinkedText, type LinkTarget } from './LinkedText'
import styles from './HorizonBands.module.css'

interface Props {
  read: HorizonRead
  evaluation?: HorizonEvaluation
  selected: boolean
  targets: LinkTarget[]
  onSelect: () => void
  onPickFeature: (key: string) => void
}

/** One horizon: its trend and momentum state, the record behind them, the ordinary range, and what every feature's record says. */
export function HorizonCard({ read, evaluation, selected, targets, onSelect, onPickFeature }: Props) {
  if (!read.available || !read.trend || !read.momentum || !read.record || !read.levels) {
    return (
      <div className={styles.card}>
        <div className={styles.top}><strong>{read.label}</strong><span className={styles.lean}>unavailable</span></div>
        <p className={styles.line}>{read.reason}</p>
      </div>
    )
  }
  const { trend, momentum, levels, implied_range: implied } = read
  const lean = read.lean ?? 'too_few'
  const basis = read.lean_basis === 'same_trend' ? read.record.same_trend : read.record.same_state
  const above = trend.state.startsWith('above')
  const lead = `Trend: ${TREND_WORDS[trend.state] ?? trend.state} ${trend.ma_days}-day average (${price(trend.ma)}), ${signedPct(trend.distance_pct)} away. ` +
    `Momentum: ${signedPct(momentum.change_pct)} over the last ${read.label}.`

  return (
    <div
      role="button"
      tabIndex={0}
      className={`${styles.card} ${selected ? styles.selected : ''}`}
      onClick={onSelect}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect() } }}
      aria-pressed={selected}
    >
      <div className={styles.top}>
        <strong>{read.label}</strong>
        <span className={`${styles.lean} ${styles[lean]}`}>{LEAN_LABEL[lean]}</span>
      </div>
      <p className={styles.line}><LinkedText text={lead} targets={targets} onPick={onPickFeature} /></p>
      <p className={styles.record}>
        {recordLine(basis, read.label)}
        {read.lean_basis === 'same_trend' ? ' (the trend state alone: trend and momentum together were too thin).' : ''}
      </p>
      {implied && (
        <p className={styles.line}>One ordinary {horizonAdjective(read.label)} move spans {price(implied.low)} to {price(implied.high)} (±{implied.sigma_pct.toFixed(1)}%).</p>
      )}
      <p className={styles.line}>
        The trend state flips {above ? 'below' : 'above'} {price(levels.trend_flips_at)}; the last {levels.recent_days} days ranged {price(levels.recent_low)} to {price(levels.recent_high)}.
      </p>
      {evaluation && <p className={styles.tally}><LinkedText text={evaluation.summary} targets={targets} onPick={onPickFeature} /></p>}
    </div>
  )
}
