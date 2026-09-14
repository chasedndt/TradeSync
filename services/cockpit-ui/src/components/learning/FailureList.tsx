import { Link } from 'react-router-dom'
import { useLearningFailures } from '../../api/hooks/useLearning'
import type { Attribution } from '../../api/learningTypes'
import { AttributionChips } from './AttributionChips'
import { CLASSIFICATION_LABELS, horizonLabel, netTone, shortSymbol, signedPct, when } from './format'
import styles from './FailureList.module.css'

const pillFor = (classification: Attribution['classification']): string =>
  classification === 'no_follow_through' ? 'pill pill--warn' : 'pill pill--bad'

/** The newest calls that lost after costs, each with the sentence that explains it. */
export function FailureList({ horizon }: { horizon: number }) {
  const { data, isLoading, error } = useLearningFailures(horizon, 12)

  return (
    <section className="panel" aria-labelledby="learning-failures-title">
      <div className="panel-heading">
        <div>
          <h3 id="learning-failures-title">Latest failures</h3>
          <p>{horizonLabel(horizon)} horizon · after round-trip costs · the readings behind each call</p>
        </div>
      </div>
      {isLoading ? (
        <p className={styles.message}>Loading failures…</p>
      ) : error ? (
        <p className={styles.message}>Failures unavailable: {(error as Error).message}</p>
      ) : !data?.failures.length ? (
        <p className={styles.message}>No failed call has been attributed at this horizon yet.</p>
      ) : (
        <ol className={styles.list}>
          {data.failures.map((failure) => (
            <FailureItem key={`${failure.opportunity_id}-${failure.horizon_minutes}`} failure={failure} />
          ))}
        </ol>
      )}
    </section>
  )
}

function FailureItem({ failure }: { failure: Attribution }) {
  return (
    <li className={styles.item}>
      <div className={styles.head}>
        <Link className={styles.market} to={`/opportunities/${failure.opportunity_id}`}>
          {shortSymbol(failure.symbol)} {failure.direction}
        </Link>
        <span className={pillFor(failure.classification)}>{CLASSIFICATION_LABELS[failure.classification]}</span>
        <span className={styles.meta}>{when(failure.opened_at)} · entry {failure.entry_regime}</span>
        <span className={`${styles.net} ${netTone(failure.net_return_pct)}`}>{signedPct(failure.net_return_pct)} net</span>
      </div>
      <p className={styles.reason}>{failure.reason}</p>
      <AttributionChips readings={failure.features} showNeutral={failure.classification === 'no_follow_through'} />
    </li>
  )
}
