import type { ReplayJudgement, ReplayOutcomeSide } from '../../api/regimeLabTypes'
import { utcTime } from '../ledger/format'
import { HORIZON_LABELS, WINDOW_LABELS, count, duration, percent, points, signed } from './format'
import { ReplayExamples } from './ReplayExamples'
import styles from './ReplayResult.module.css'

const returnPct = (value: number | null | undefined) => (value == null ? '—' : `${signed(value, 3)}%`)

interface OutcomeRow {
  label: string
  side: (side: ReplayOutcomeSide) => string
  delta: string
}

/** What the challenger changed on the stored decisions, and how each rulebook's admitted set fared where outcomes exist. */
export function ReplayResult({ result, current }: { result: ReplayJudgement; current: boolean }) {
  const { decisions, outcomes, window: span } = result
  const rows: OutcomeRow[] = [
    {
      label: 'Admitted with an outcome (n)',
      side: (side) => count(side.admitted_with_outcome),
      delta: signed(outcomes.challenger.admitted_with_outcome - outcomes.baseline.admitted_with_outcome, 0),
    },
    { label: 'Hit rate', side: (side) => percent(side.hit_rate), delta: points(outcomes.delta.hit_rate) },
    { label: 'Hit rate by luck for its long/short mix', side: (side) => percent(side.expected_hit_rate), delta: '' },
    { label: 'Skill: hit rate minus luck', side: (side) => points(side.skill), delta: points(outcomes.delta.skill) },
    { label: 'Mean signed return', side: (side) => returnPct(side.mean_signed_return_pct), delta: returnPct(outcomes.delta.mean_signed_return_pct) },
  ]

  return (
    <div className={styles.result} aria-live="polite">
      <div className={styles.summary}>
        <h4>Replay judgement</h4>
        <p>{describeSpan(result)}</p>
        {!current && <p className="tone-warn">Weights or replay settings changed after this replay; evaluate again before saving.</p>}
      </div>
      <ul className={styles.counts}>
        <Count label="Decisions changed" value={decisions.changed} sub={`of ${count(decisions.replayed)} replayed`} />
        <Count label="Admissions gained" value={decisions.admissions_gained} sub={`challenger admits ${count(result.challenger.admitted)}`} />
        <Count label="Admissions lost" value={decisions.admissions_lost} sub={`baseline admits ${count(result.baseline.admitted)}`} />
        <Count label="Direction flips" value={decisions.direction_flips} sub="weights never set a side" />
      </ul>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <caption>
            {count(outcomes.cases_with_outcome)} replayed decisions have a measured {HORIZON_LABELS[span.horizon_minutes]} outcome: the ones that opened a paper opportunity
          </caption>
          <thead>
            <tr>
              <th scope="col"><span className="sr-only">Measure</span></th>
              <th scope="col">Baseline</th>
              <th scope="col">Challenger</th>
              <th scope="col">Difference</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <th scope="row">{row.label}</th>
                <td>{row.side(outcomes.baseline)}</td>
                <td>{row.side(outcomes.challenger)}</td>
                <td>{row.delta}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ReplayExamples examples={result.changed_examples} />
      <p className={styles.note}>{result.note}</p>
    </div>
  )
}

function Count({ label, value, sub }: { label: string; value: number; sub: string }) {
  return (
    <li className={styles.count}>
      <span>{label}</span>
      <strong>{count(value)}</strong>
      <small>{sub}</small>
    </li>
  )
}

/** Which decisions were replayed, how they were sampled, and how far back refusals reach. */
function describeSpan({ window: span, decisions }: ReplayJudgement): string {
  const scope = span.symbol ?? 'all markets'
  if (span.decisions_in_window === 0) {
    return `${WINDOW_LABELS[span.hours]}, ${scope}: no decisions were recorded, so there is nothing to replay.`
  }
  const sample = span.sample_bucket_seconds <= 60
    ? 'every decision'
    : `one decision per market per ${duration(span.sample_bucket_seconds * 1000)}`
  const refusals = span.refusals_available_since
    ? `refused decisions available since ${utcTime(span.refusals_available_since)} UTC`
    : 'no refused decisions stored in this window'
  const skipped = span.skipped_unreplayable > 0 ? ` · ${count(span.skipped_unreplayable)} could not be replayed` : ''
  return `${WINDOW_LABELS[span.hours]}, ${scope} · ${count(decisions.replayed)} of ${count(span.decisions_in_window)} decisions replayed (${sample}) · ${refusals}, kept ${span.refusal_retention_days} days${skipped}`
}
