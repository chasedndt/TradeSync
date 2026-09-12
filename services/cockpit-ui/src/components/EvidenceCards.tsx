import { useEvidenceCards } from '../api/hooks/useEvidenceCards'
import type { EvidenceCard, EvidenceCardCell } from '../api/types'
import styles from './EvidenceCards.module.css'

/**
 * Evidence cards: one per candidate feature, scoring or context-only alike.
 *
 * A feature's sign at entry is scored as a directional call in both
 * polarities; every cell on every card is Holm-adjusted together with the
 * skill gate's costs. "Earned" is positive skill that also held out of
 * sample. The panel reports; it cannot change the catalog. Granting a weight
 * is an operator decision with a change record.
 */
export function EvidenceCards({ symbol }: { symbol?: string }) {
  const { data, isLoading, isError } = useEvidenceCards(symbol)

  if (isError) return <section className="panel lab-section"><p className="tone-bad">Evidence cards unavailable. Nothing is inferred.</p></section>
  if (isLoading || !data) return <section className="panel lab-section"><p className="tone-dim">Measuring evidence cards… (every cell bootstrapped together)</p></section>

  const earned = data.cards.filter((c) => c.earned).length
  return (
    <section className="panel lab-section" aria-labelledby="evidence-cards-title">
      <div className="panel-heading">
        <div>
          <h2 id="evidence-cards-title">Evidence cards</h2>
          <p>
            Weights earned by measured skill, not by more screens · catalog v{data.catalog_version} · {data.cards.length} features · Holm across {data.cells_assessed_together} cells
            {symbol ? ` · ${symbol}` : ' · all symbols'}
          </p>
        </div>
        <span className={earned > 0 ? 'tone-good' : 'tone-dim'}>{earned} earned</span>
      </div>

      <div className={styles.grid}>
        {data.cards.map((card) => <Card key={card.feature_id} card={card} />)}
      </div>
      <p className={styles.foot}>
        {data.note} {data.entries_pending > 0 ? `${data.entries_pending} opportunities not yet feature-labelled.` : 'Every opportunity is feature-labelled.'} Costs: {data.costs.source}.
      </p>
    </section>
  )
}

function Card({ card }: { card: EvidenceCard }) {
  const total = card.entries_with_reading + card.entries_without_reading
  return (
    <article className={`${styles.card} ${card.earned ? styles.earned : ''}`} aria-label={card.feature_id}>
      <div className={styles.head}>
        <span className={styles.id}>{card.feature_id}</span>
        <span className={`${styles.standing} ${card.standing === 'scoring' ? styles.scoring : styles.context}`}>
          {card.standing === 'scoring' ? 'scoring' : 'context only'}
        </span>
      </div>
      <span className={`${styles.verdict} ${card.earned ? 'tone-good' : 'tone-dim'}`}>
        {card.earned ? `EARNED · ${card.earned_by.join(', ')}` : 'not earned'}
      </span>
      <span className={styles.coverage}>
        {total === 0
          ? 'no entry readings recorded yet'
          : `${card.entries_with_reading} of ${total} entries had a reading${card.abstained > 0 ? ` · ${card.abstained} abstained (zero)` : ''}`}
      </span>
      {card.cells.length > 0 && (
        <table className={styles.cells}>
          <thead><tr><th>h</th><th>pol</th><th>n / indep</th><th>skill</th><th>z</th><th>hold-out</th><th>net %</th></tr></thead>
          <tbody>{card.cells.map((c) => <Row key={`${c.horizon_minutes}-${c.polarity}`} c={c} />)}</tbody>
        </table>
      )}
      <p className={styles.next}>{card.next_step}</p>
      {card.decision_role && <p className={styles.role}>{card.decision_role}</p>}
    </article>
  )
}

function Row({ c }: { c: EvidenceCardCell }) {
  const pts = (x: number | null) => (x == null ? '—' : `${x * 100 >= 0 ? '+' : ''}${(x * 100).toFixed(1)}`)
  const tone = c.earned ? 'tone-good' : c.detectable ? 'tone-warn' : 'tone-dim'
  return (
    <tr className={tone} title={c.notes.join(' ')}>
      <td>{c.horizon_minutes}m</td>
      <td>{c.polarity === 'as_read' ? 'as read' : 'inverted'}</td>
      <td>{c.measured} / {c.independent_pooled}</td>
      <td>{pts(c.skill)}</td>
      <td>{c.z == null ? '—' : c.z.toFixed(2)}</td>
      <td>{pts(c.holdout_skill)}</td>
      <td>{c.mean_net_return_pct == null ? '—' : c.mean_net_return_pct.toFixed(3)}</td>
    </tr>
  )
}
