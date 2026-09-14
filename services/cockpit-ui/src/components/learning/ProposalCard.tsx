import { useState } from 'react'
import { useAdoptProposal, useRejectProposal } from '../../api/hooks/useLearningActions'
import type { Proposal, WeightChange } from '../../api/learningTypes'
import { humanize } from '../ledger/format'
import { ReplayComparison } from './ReplayComparison'
import { VERDICT_LABELS, horizonLabel, when } from './format'
import styles from './ProposalCard.module.css'

const STATUS_PILL: Record<Proposal['status'], string> = {
  proposed: 'pill pill--warn',
  adopted: 'pill pill--good',
  rejected: 'pill pill--bad',
  superseded: 'pill',
}

const moved = (record: Record<string, WeightChange> | undefined) =>
  Object.entries(record ?? {}).filter(([, change]) => Math.abs(change.after - change.before) > 1e-9)

/** One challenger rulebook: what it changes, the walk-forward evidence, and the operator's decision. */
export function ProposalCard({ proposal, operator }: { proposal: Proposal; operator: string }) {
  const [note, setNote] = useState('')
  const adopt = useAdoptProposal()
  const reject = useRejectProposal()
  const name = operator.trim()
  const named = name.length >= 2
  const busy = adopt.isPending || reject.isPending
  const blockChanges = moved(proposal.weights.blocks)
  const featureChanges = moved(proposal.weights.features)
  const decision = { decided_by: name, note: note.trim() }

  const onAdopt = () => {
    if (window.confirm(`Adopt ${proposal.version} as the active paper rulebook? The paper scorer uses these weights from its next cycle. Execution stays not connected, and Revert restores the previous rulebook.`)) {
      adopt.mutate({ id: proposal.id, decision })
    }
  }
  const onReject = () => {
    if (window.confirm(`Reject ${proposal.version}? It stays in the record and the active rulebook does not change.`)) {
      reject.mutate({ id: proposal.id, decision })
    }
  }

  return (
    <article className={styles.card} aria-labelledby={`proposal-${proposal.id}`}>
      <header className={styles.head}>
        <h4 id={`proposal-${proposal.id}`} className={styles.version}>{proposal.version}</h4>
        <span className={STATUS_PILL[proposal.status]}>{proposal.status}</span>
        <span className={styles.meta}>
          {horizonLabel(proposal.target_horizon_minutes)} horizon · built on {proposal.parent_version} · {when(proposal.created_at)} by {proposal.created_by}
        </span>
      </header>
      <p className={styles.hypothesis}>{proposal.hypothesis}</p>
      {(blockChanges.length > 0 || featureChanges.length > 0) && (
        <ul className={styles.changes} aria-label="Weight changes">
          {blockChanges.map(([key, change]) => <ChangeRow key={`block-${key}`} name={`${humanize(key)} block`} change={change} digits={3} />)}
          {featureChanges.map(([key, change]) => <ChangeRow key={`feature-${key}`} name={key} change={change} digits={2} mono />)}
        </ul>
      )}
      <ReplayComparison proposal={proposal} />
      {proposal.status === 'proposed' ? (
        <div className={styles.actions}>
          <label className={styles.note}>
            Decision note (optional)
            <input value={note} maxLength={500} onChange={(event) => setNote(event.target.value)} placeholder="Why you adopt or reject it" />
          </label>
          <button type="button" className="chip chip--active" disabled={!named || busy} onClick={onAdopt}>
            {adopt.isPending ? 'Adopting…' : 'Adopt'}
          </button>
          <button type="button" className="chip" disabled={!named || busy} onClick={onReject}>
            {reject.isPending ? 'Rejecting…' : 'Reject'}
          </button>
          {!named && <span className={styles.hint}>Enter your name above to decide.</span>}
        </div>
      ) : (
        <p className={styles.decided}>
          {proposal.decided_by ? `${proposal.status} by ${proposal.decided_by} ${when(proposal.decided_at)}` : proposal.status}
          {proposal.decision_note ? ` · ${proposal.decision_note}` : ''}
          {proposal.reverted_at ? ` · reverted ${when(proposal.reverted_at)}` : ''}
        </p>
      )}
      {adopt.isError && <p role="alert" className={`${styles.decided} tone-bad`}>{adopt.error.message}</p>}
      {reject.isError && <p role="alert" className={`${styles.decided} tone-bad`}>{reject.error.message}</p>}
      {adopt.isSuccess && <p role="status" className={styles.decided}>{adopt.data.note}</p>}
    </article>
  )
}

function ChangeRow({ name, change, digits, mono = false }: { name: string; change: WeightChange; digits: number; mono?: boolean }) {
  return (
    <li>
      <span className={mono ? styles.mono : undefined}>{name}</span>
      <span className={styles.weights}>
        {change.before.toFixed(digits)} → {change.after.toFixed(digits)}
        <span className="sr-only">{change.after > change.before ? ' raised' : ' lowered'}</span>
      </span>
      <span className={styles.because}>{VERDICT_LABELS[change.verdict].toLowerCase()}</span>
    </li>
  )
}
