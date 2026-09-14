import { useActiveRulebook } from '../../api/hooks/useLearning'
import { useRevertRulebook } from '../../api/hooks/useLearningActions'
import { humanize, since } from '../ledger/format'
import { when } from './format'
import styles from './ActiveRulebook.module.css'

/** Which weights the paper scorer is using, whether its newest verdict used them, and the way back. */
export function ActiveRulebook({ operator }: { operator: string }) {
  const { data, isLoading, error } = useActiveRulebook()
  const revert = useRevertRulebook()
  const name = operator.trim()

  if (isLoading) return <p className={styles.message}>Reading the active rulebook…</p>
  if (error || !data) return <p className={styles.message}>Active rulebook unavailable{error ? `: ${(error as Error).message}` : '.'}</p>

  const { active, scorer_last_used: used, scorer_in_step: inStep } = data
  const adopted = active.source === 'database'
  const featureWeights = Object.entries(active.feature_weights)

  const onRevert = () => {
    if (window.confirm(`Revert ${active.version}? The rulebook active before it is restored, and the paper scorer uses it from its next cycle. Execution stays not connected.`)) {
      revert.mutate({ decided_by: name, note: 'Reverted from the Learning view' })
    }
  }

  return (
    <div className={styles.active}>
      <div className={styles.line}>
        <span className={styles.label}>Paper scorer weights</span>
        <strong className={styles.version}>{active.version}</strong>
        <span className={styles.meta}>
          {adopted ? `adopted by ${active.activated_by ?? 'an unnamed operator'} ${when(active.activated_at)}` : 'the rulebook file; no adopted version is active'}
        </span>
        {adopted && (
          <button type="button" className="chip" disabled={name.length < 2 || revert.isPending} onClick={onRevert}>
            {revert.isPending ? 'Reverting…' : 'Revert'}
          </button>
        )}
      </div>
      <p className={styles.meta}>
        <span aria-hidden="true" className={inStep ? 'tone-good' : 'tone-warn'}>{inStep ? '✓' : '!'}</span>{' '}
        {used
          ? `The scorer's newest verdict (${since(used.at)}) used ${used.version ?? 'an unrecorded version'}${inStep ? ', the active rulebook.' : '; it switches to the active rulebook on its next cycle.'}`
          : 'The scorer has not recorded a verdict yet.'}
      </p>
      <p className={styles.weights}>
        {Object.entries(active.weights).map(([block, weight]) => `${humanize(block)} ${weight.toFixed(3)}`).join(' · ')}
        {featureWeights.length > 0 && ` · feature multipliers: ${featureWeights.map(([id, weight]) => `${id} ×${weight}`).join(', ')}`}
      </p>
      {revert.isError && <p role="alert" className={`${styles.meta} tone-bad`}>{revert.error.message}</p>}
      {revert.isSuccess && <p role="status" className={styles.meta}>{revert.data.note ?? `Restored ${revert.data.version}.`}</p>}
    </div>
  )
}
