import type { FeatureEvaluation, HorizonEvaluation } from '../../api/horizonTypes'
import { LEAN_LABEL, adjective, heldOutLine, pct, signedPct } from './timeframeText'
import styles from './EvidenceTable.module.css'

interface Props {
  evaluation?: HorizonEvaluation
  horizonLabel: string
  active: Set<string>
  onToggle: (key: string) => void
  highlight: string | null
}

/**
 * Every feature at the selected horizon: what it reads today, the record for
 * today's state, how it did out of sample, the weight that earned it, and which
 * way it pushes the weighted reading. Features with earned weight come first.
 */
export function EvidenceTable({ evaluation, horizonLabel, active, onToggle, highlight }: Props) {
  if (!evaluation) return null
  const rows = [...evaluation.features].sort((a, b) => b.weight - a.weight || (a.kind === b.kind ? 0 : a.kind === 'directional' ? -1 : 1))
  return (
    <section className={`panel ${styles.panel}`} aria-labelledby="evidence-title">
      <header className={styles.head}>
        <h3 id="evidence-title">Feature evidence over {horizonLabel}</h3>
        <p>
          Weight is the skill each feature showed on the newest 30% of history after learning on the older 70%, above what chance
          would score. All {adjective(horizonLabel)} windows rose {pct(evaluation.base_share_up)} of the time.
        </p>
      </header>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr><th>Feature</th><th>Today</th><th>Record for today's state</th><th>Out of sample</th><th>Weight</th><th>Pushes</th><th>Chart</th></tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <Row key={f.key} feature={f} shown={active.has(f.key)} highlighted={highlight === f.key} onToggle={() => onToggle(f.key)} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function Row({ feature: f, shown, highlighted, onToggle }: { feature: FeatureEvaluation; shown: boolean; highlighted: boolean; onToggle: () => void }) {
  const earned = f.weight > 0
  const push = !earned ? 'no weight' : f.current_lean > 0 ? '▲ higher' : f.current_lean < 0 ? '▼ lower' : 'neither way'
  const pushClass = !earned ? styles.muted : f.current_lean > 0 ? styles.upText : f.current_lean < 0 ? styles.downText : ''
  return (
    <tr id={`feature-${f.key}`} className={highlighted ? styles.flash : undefined}>
      <th scope="row" data-label="Feature">
        <span className={styles.name} title={f.measures}>{f.label}</span>
        <span className={styles.kind}>{f.kind === 'directional' ? 'direction' : 'context'}</span>
      </th>
      <td data-label="Today" className={styles.text}>{f.text}</td>
      <td data-label="Record">
        <span className={`${styles.badge} ${styles[f.record_lean]}`}>{LEAN_LABEL[f.record_lean]}</span>
        <span className={styles.small}>
          {f.record.days ? `up ${pct(f.record.share_up)} · median ${signedPct(f.record.median_pct, 2)} · ${f.record.independent_windows} windows` : 'no comparable bars'}
        </span>
      </td>
      <td data-label="Out of sample" className={styles.small}>{heldOutLine(f.held_out)}</td>
      <td data-label="Weight">
        <span className={styles.bar} aria-hidden="true"><i style={{ width: `${Math.round(f.weight * 100)}%` }} /></span>
        <span className={styles.num}>{f.weight.toFixed(2)}</span>
      </td>
      <td data-label="Pushes" className={pushClass}>{push}</td>
      <td data-label="Chart">
        <button type="button" className={shown ? 'chip chip--active' : 'chip'} aria-pressed={shown} onClick={onToggle}>
          {shown ? 'on chart' : 'show'}
        </button>
      </td>
    </tr>
  )
}
