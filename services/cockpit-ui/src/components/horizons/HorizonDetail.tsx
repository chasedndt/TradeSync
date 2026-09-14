import type { HorizonEvaluation, HorizonRead } from '../../api/horizonTypes'
import { price } from '../ledger/format'
import { LinkedText, type LinkTarget } from './LinkedText'
import { INTERVAL_WORDS, LEAN_LABEL, TREND_WORDS, capitalise, recordLine, signedPct, spanWords } from './timeframeText'
import styles from './HorizonDetail.module.css'

interface Props {
  read: HorizonRead
  evaluation?: HorizonEvaluation
  targets: LinkTarget[]
  onPick: (key: string) => void
}

/** The selected horizon in words: the weighted reading, trend, momentum, the record, the ordinary move and the levels. */
export function HorizonDetail({ read, evaluation, targets, onPick }: Props) {
  if (!read.available || !read.trend || !read.momentum || !read.record || !read.levels) {
    return (
      <section className={`panel ${styles.panel}`}>
        <h3 className={styles.title}>{read.label} ahead</h3>
        <p className={styles.muted}>{read.reason ?? 'Not measured yet.'}</p>
      </section>
    )
  }
  const { trend, momentum, levels, implied_range: implied } = read
  const basis = read.lean_basis === 'same_trend' ? read.record.same_trend : read.record.same_state
  const above = trend.state.startsWith('above')
  const combined = evaluation?.combined
  const lean = read.lean ?? 'too_few'
  return (
    <section className={`panel ${styles.panel}`} aria-labelledby="horizon-detail-title">
      <header className={styles.head}>
        <h3 id="horizon-detail-title" className={styles.title}>{read.label} ahead</h3>
        <span className={styles.sub}>{INTERVAL_WORDS[read.interval]} candles</span>
        <span className={`${styles.badge} ${styles[lean]}`}>{LEAN_LABEL[lean]}</span>
      </header>
      {combined && (
        <p className={`${styles.weighted} ${styles[`w_${combined.lean}`]}`}>
          <LinkedText text={combined.sentence} targets={targets} onPick={onPick} />
        </p>
      )}
      <dl className={styles.facts}>
        <dt>Trend</dt>
        <dd>
          <LinkedText text={`${capitalise(TREND_WORDS[trend.state] ?? trend.state)} ${trend.ma_label} average (${price(trend.ma)}), ${signedPct(trend.distance_pct)} away.`} targets={targets} onPick={onPick} />
        </dd>
        <dt>Momentum</dt>
        <dd>{signedPct(momentum.change_pct, 2)} over the last {read.label}.</dd>
        <dt>Record</dt>
        <dd>{recordLine(basis, read.label)}{read.lean_basis === 'same_trend' ? ' Trend state alone: trend and momentum together were too thin.' : ''}</dd>
        {implied && (
          <>
            <dt>Ordinary move</dt>
            <dd>{price(implied.low)} to {price(implied.high)} (±{implied.sigma_pct.toFixed(2)}%).</dd>
          </>
        )}
        <dt>Levels</dt>
        <dd>Trend flips {above ? 'below' : 'above'} {price(levels.trend_flips_at)}; the last {spanWords(levels.recent_label)} ranged {price(levels.recent_low)} to {price(levels.recent_high)}.</dd>
      </dl>
      {evaluation && <p className={styles.tally}><LinkedText text={evaluation.summary} targets={targets} onPick={onPick} /></p>}
    </section>
  )
}
