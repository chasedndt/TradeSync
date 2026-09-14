import { useState } from 'react'
import { useLearningVerdicts } from '../../api/hooks/useLearning'
import type { GroupEvidence, VerdictsResponse } from '../../api/learningTypes'
import { VERDICT_LABELS, horizonLabel, netTone, shareRange, sharePct, signedPct, verdictTone } from './format'
import styles from './VerdictTable.module.css'

type Dimension = 'feature' | 'block' | 'regime' | 'symbol'

const DIMENSIONS: { id: Dimension; label: string }[] = [
  { id: 'feature', label: 'Features' },
  { id: 'block', label: 'Blocks' },
  { id: 'regime', label: 'Entry regime' },
  { id: 'symbol', label: 'Symbols' },
]
const ORDER = { hurting: 0, helping: 1, no_evidence: 2 } as const

/**
 * Which readings mislead more often than chance, and which calls lost, by group.
 * The verdict follows the name so it stays in view when the table scrolls sideways.
 */
export function VerdictTable({ horizon, days }: { horizon: number; days: number }) {
  const [dimension, setDimension] = useState<Dimension>('feature')
  const { data, isLoading, error } = useLearningVerdicts(horizon, days)
  const perReading = dimension === 'feature' || dimension === 'block'
  const rows = data ? [...data[dimension]].sort((a, b) => ORDER[a.verdict] - ORDER[b.verdict] || b.decided - a.decided) : []

  return (
    <section className="panel" aria-labelledby="learning-verdicts-title">
      <div className="panel-heading">
        <div>
          <h3 id="learning-verdicts-title">What the evidence says</h3>
          <p>{horizonLabel(horizon)} horizon · last {days} days · each rate against what chance alone would produce</p>
        </div>
      </div>
      <div className={styles.controls} role="group" aria-label="Group by">
        {DIMENSIONS.map((item) => (
          <button key={item.id} type="button" className={dimension === item.id ? 'chip chip--active' : 'chip'} aria-pressed={dimension === item.id} onClick={() => setDimension(item.id)}>
            {item.label}
          </button>
        ))}
      </div>
      {isLoading ? (
        <p className={styles.message}>Loading verdicts…</p>
      ) : error ? (
        <p className={styles.message}>Verdicts unavailable: {(error as Error).message}</p>
      ) : !rows.length ? (
        <p className={styles.message}>Nothing attributed at this horizon in this window yet.</p>
      ) : (
        <div className={styles.scroll}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">{perReading ? 'Reading' : 'Group'}</th>
                <th scope="col">Verdict</th>
                {perReading && <th scope="col">Role</th>}
                <th scope="col">Decisive</th>
                <th scope="col">{perReading ? 'Misled' : 'Lost'} (95%)</th>
                <th scope="col">Chance</th>
                <th scope="col">Eff. sample</th>
                {perReading ? <th scope="col">Net when it agreed</th> : <th scope="col">Mean net</th>}
                {perReading && <th scope="col">Net when it disagreed</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((group) => <VerdictRow key={`${group.key}-${group.role}`} group={group} perReading={perReading} />)}
            </tbody>
          </table>
        </div>
      )}
      {data && <PolicyNote policy={data.policy} />}
    </section>
  )
}

function VerdictRow({ group, perReading }: { group: GroupEvidence; perReading: boolean }) {
  return (
    <tr>
      <th scope="row" className={styles.name}>{group.label}</th>
      <td className={verdictTone(group.verdict)}>{VERDICT_LABELS[group.verdict]}</td>
      {perReading && <td>{group.role ?? '—'}</td>}
      <td className={styles.num}>{group.decided.toLocaleString()}</td>
      <td className={styles.num}>
        {sharePct(group.misled_rate)}
        <span className={styles.range}>{shareRange(group.misled_low, group.misled_high)}</span>
      </td>
      <td className={styles.num}>{sharePct(group.chance_misled_rate)}</td>
      <td className={styles.num}>{Math.round(group.effective_samples)}</td>
      {perReading ? (
        <td className={`${styles.num} ${netTone(group.mean_net_agreed_pct)}`}>
          {signedPct(group.mean_net_agreed_pct, 3)} <span className={styles.count}>({group.agreed})</span>
        </td>
      ) : (
        <td className={`${styles.num} ${netTone(group.mean_net_return_pct)}`}>{signedPct(group.mean_net_return_pct, 3)}</td>
      )}
      {perReading && (
        <td className={`${styles.num} ${netTone(group.mean_net_disagreed_pct)}`}>
          {signedPct(group.mean_net_disagreed_pct, 3)} <span className={styles.count}>({group.disagreed})</span>
        </td>
      )}
    </tr>
  )
}

function PolicyNote({ policy }: { policy: VerdictsResponse['policy'] }) {
  return (
    <p className={styles.foot}>
      A verdict needs at least {policy.min_decided} decisive results, an effective sample of {policy.min_effective}, and a 95%
      interval that excludes chance. Moves inside the round-trip cost count as neither right nor wrong. Proposals change block
      weights and directional features only.
    </p>
  )
}
