import { useRegimeLabExperiments } from '../../api/hooks/useRegimeLab'
import type { RegimeLabExperiment } from '../../api/regimeLabTypes'
import { since } from '../ledger/format'
import { HORIZON_LABELS, WINDOW_LABELS, blockLabel, count, points } from './format'
import styles from './RecentExperiments.module.css'

/** Saved drafts, newest first, each with its hypothesis, weights and the replay measured when it was saved. */
export function RecentExperiments() {
  const { data, error, isLoading } = useRegimeLabExperiments(8)
  return (
    <section className={`panel ${styles.panel}`} aria-labelledby="saved-drafts-title">
      <div className="panel-heading">
        <div>
          <h3 id="saved-drafts-title">Saved drafts</h3>
          <p>Newest first · each keeps the replay measured when it was saved · no activation path</p>
        </div>
      </div>
      {isLoading && <p className={styles.state}>Loading saved drafts…</p>}
      {error && <p className={`${styles.state} tone-bad`}>Saved drafts unavailable: {error.message}</p>}
      {data && data.experiments.length === 0 && <p className={styles.state}>No drafts saved yet.</p>}
      {data && data.experiments.length > 0 && (
        <ol className={styles.list}>
          {data.experiments.map((experiment) => <Draft key={experiment.id} experiment={experiment} />)}
        </ol>
      )}
    </section>
  )
}

function Draft({ experiment }: { experiment: RegimeLabExperiment }) {
  const weights = Object.entries(experiment.weights)
    .map(([block, weight]) => `${blockLabel(block)} ${weight == null ? '—' : weight.toFixed(2)}`)
    .join(' · ')
  return (
    <li className={styles.item}>
      <div className={styles.top}>
        <strong>{experiment.name}</strong>
        <span>{experiment.challenger_version} · saved {since(experiment.created_at)}</span>
      </div>
      <p className={styles.hypothesis}>{experiment.hypothesis}</p>
      <p className={styles.weights}>{weights}</p>
      {experiment.replay
        ? <p className={styles.judgement}>{judgement(experiment, experiment.replay)}</p>
        : <p className={styles.unjudged}>Saved before challengers were judged by replay.</p>}
    </li>
  )
}

function judgement(experiment: RegimeLabExperiment, replay: NonNullable<RegimeLabExperiment['replay']>): string {
  const { decisions, outcomes } = replay
  const window = experiment.window_hours ? WINDOW_LABELS[experiment.window_hours] : 'Unrecorded window'
  const horizon = experiment.horizon_minutes ? `${HORIZON_LABELS[experiment.horizon_minutes]} outcomes` : 'unrecorded horizon'
  return [
    `${window}, ${experiment.symbol ?? 'all markets'}, ${horizon}`,
    `${count(decisions.changed)} of ${count(decisions.replayed)} decisions changed (gained ${count(decisions.admissions_gained)}, lost ${count(decisions.admissions_lost)})`,
    `skill ${points(outcomes.baseline.skill)} → ${points(outcomes.challenger.skill)} (n ${count(outcomes.baseline.admitted_with_outcome)} → ${count(outcomes.challenger.admitted_with_outcome)})`,
  ].join(' · ')
}
