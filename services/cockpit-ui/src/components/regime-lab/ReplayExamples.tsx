import type { ReplayChangedExample } from '../../api/regimeLabTypes'
import { percent } from './format'
import styles from './ReplayResult.module.css'

const CHANGE_LABELS: Record<ReplayChangedExample['change'], string> = {
  admissions_gained: 'admission gained',
  admissions_lost: 'admission lost',
  direction_flips: 'direction flipped',
}

/** The newest decisions the challenger decided differently, with the coverage each rulebook saw. */
export function ReplayExamples({ examples }: { examples: ReplayChangedExample[] }) {
  if (examples.length === 0) return null
  return (
    <details className={styles.examples}>
      <summary>Newest changed decisions ({examples.length})</summary>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">When (UTC)</th>
              <th scope="col">Market</th>
              <th scope="col">Change</th>
              <th scope="col">Baseline</th>
              <th scope="col">Challenger</th>
              <th scope="col">Coverage</th>
              <th scope="col">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {examples.map((example) => (
              <tr key={example.signal_id}>
                <td>{new Date(example.evaluated_at_ms).toISOString().slice(5, 16).replace('T', ' ')}</td>
                <td>{example.symbol}</td>
                <td>{CHANGE_LABELS[example.change]}</td>
                <td>{example.baseline}</td>
                <td>{example.challenger}</td>
                <td>{percent(example.baseline_coverage, 0)} → {percent(example.challenger_coverage, 0)}</td>
                <td>{example.has_outcome ? 'measured' : 'none'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}
