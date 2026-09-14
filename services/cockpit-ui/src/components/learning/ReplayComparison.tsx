import type { Proposal, ReplayMetrics } from '../../api/learningTypes'
import { netTone, pctRange, shareRange, sharePct, signedPct, whenSeconds } from './format'
import styles from './ReplayComparison.module.css'

const ASSESSMENT: Record<string, string> = {
  replay_favours_proposal: 'Replay on the newest decisions favours the proposal',
  replay_favours_baseline: 'Replay on the newest decisions favours the current rulebook',
  mixed: 'Mixed: one measure improved and the other did not',
  insufficient_test_evidence: 'Too little test evidence to judge either way',
}

/** The walk-forward evidence behind one proposal: where it learned, where it was tested, and how both rulebooks did. */
export function ReplayComparison({ proposal }: { proposal: Proposal }) {
  const { baseline, proposal: challenger, assessment, note } = proposal.replay
  const span = proposal.evidence.window
  if (!baseline || !challenger) return null

  return (
    <div className={styles.replay}>
      <p className={styles.assessment}><strong>{ASSESSMENT[assessment ?? ''] ?? assessment ?? 'Not assessed'}</strong></p>
      {span && (
        <p className={styles.window}>
          Learned on {span.learn.decisions.toLocaleString()} decisions ({whenSeconds(span.learn.first_opened_at_s)} to{' '}
          {whenSeconds(span.learn.last_opened_at_s)}{span.learn.purged ? `, leaving out ${span.learn.purged} whose outcome overlapped the test period` : ''});
          tested on the newest {span.test.decisions.toLocaleString()} ({whenSeconds(span.test.first_opened_at_s)} to{' '}
          {whenSeconds(span.test.last_opened_at_s)}).
        </p>
      )}
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Rulebook</th>
              <th scope="col">Scored</th>
              <th scope="col">Admitted</th>
              <th scope="col">Refused</th>
              <th scope="col">Flipped</th>
              <th scope="col">Won after costs (95%)</th>
              <th scope="col">Mean net (95%)</th>
            </tr>
          </thead>
          <tbody>
            <MetricsRow name="Current" metrics={baseline} />
            <MetricsRow name="Proposal" metrics={challenger} />
          </tbody>
        </table>
      </div>
      <p className={styles.note}>
        {note}
        {baseline.reproduced_share != null ? ` The current rulebook's replay reproduced ${sharePct(baseline.reproduced_share)} of the stored calls.` : ''}
      </p>
    </div>
  )
}

function MetricsRow({ name, metrics }: { name: string; metrics: ReplayMetrics }) {
  return (
    <tr>
      <th scope="row">
        {name}
        <span className={styles.version}>{metrics.rulebook_version}</span>
      </th>
      <td>{metrics.decisions.toLocaleString()}</td>
      <td>{metrics.admitted.toLocaleString()}</td>
      <td>{metrics.refused.toLocaleString()}</td>
      <td>{metrics.flipped.toLocaleString()}</td>
      <td>
        {sharePct(metrics.net_hit_rate)}
        <span className={styles.range}>{shareRange(metrics.net_hit_rate_low, metrics.net_hit_rate_high)}</span>
      </td>
      <td className={netTone(metrics.mean_net_return_pct)}>
        {signedPct(metrics.mean_net_return_pct, 3)}
        <span className={styles.range}>{pctRange(metrics.mean_net_return_low, metrics.mean_net_return_high, 3)}</span>
      </td>
    </tr>
  )
}
