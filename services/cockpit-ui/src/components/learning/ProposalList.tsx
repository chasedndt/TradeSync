import { useLearningProposals } from '../../api/hooks/useLearning'
import { useGenerateProposal } from '../../api/hooks/useLearningActions'
import { ActiveRulebook } from './ActiveRulebook'
import { ProposalCard } from './ProposalCard'
import { horizonLabel, when } from './format'
import styles from './ProposalList.module.css'

/** The active weights, open proposals awaiting a decision, and the proposals already decided. */
export function ProposalList({ operator, horizon }: { operator: string; horizon: number }) {
  const { data, isLoading, error } = useLearningProposals()
  const generate = useGenerateProposal()
  const name = operator.trim()
  const proposals = data?.proposals ?? []
  const open = proposals.filter((proposal) => proposal.status === 'proposed')
  const earlier = proposals.filter((proposal) => proposal.status !== 'proposed')

  const runText = generate.data ? generate.data.reason : data?.last_run ? (data.last_run.error ?? data.last_run.reason ?? '') : ''
  const runAt = generate.data ? null : data?.last_run?.at ?? null

  return (
    <section className="panel" aria-labelledby="learning-proposals-title">
      <div className={`panel-heading ${styles.heading}`}>
        <div>
          <h3 id="learning-proposals-title">Weight proposals</h3>
          <p>learned on older decisions, replayed on the newest · adopted only by an operator</p>
        </div>
        <button
          type="button"
          className={`chip ${styles.runButton}`}
          disabled={name.length < 2 || generate.isPending}
          title={name.length < 2 ? 'Enter your name above first' : undefined}
          onClick={() => generate.mutate({ requestedBy: name, horizon })}
        >
          {generate.isPending ? 'Running walk-forward…' : `Run walk-forward (${horizonLabel(horizon)})`}
        </button>
      </div>
      <ActiveRulebook operator={operator} />
      {runText && <p className={styles.run}>Latest walk-forward{runAt ? ` (${when(runAt)})` : ''}: {runText}</p>}
      {generate.isError && <p role="alert" className={`${styles.run} tone-bad`}>{generate.error.message}</p>}
      {isLoading ? (
        <p className={styles.message}>Loading proposals…</p>
      ) : error ? (
        <p className={styles.message}>Proposals unavailable: {(error as Error).message}</p>
      ) : open.length === 0 ? (
        <p className={styles.message}>
          No open proposal. The learning job runs the walk-forward every six hours and proposes a change only when a feature or
          block has a verdict.
        </p>
      ) : (
        <div className={styles.cards}>
          {open.map((proposal) => <ProposalCard key={proposal.id} proposal={proposal} operator={operator} />)}
        </div>
      )}
      {earlier.length > 0 && (
        <details className={styles.earlier}>
          <summary>Earlier proposals ({earlier.length})</summary>
          <div className={styles.cards}>
            {earlier.map((proposal) => <ProposalCard key={proposal.id} proposal={proposal} operator={operator} />)}
          </div>
        </details>
      )}
    </section>
  )
}
