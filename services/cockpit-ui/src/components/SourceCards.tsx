import { useSourceCards } from '../api/hooks/useAgentFeed'
import type { SourceCard, SourceCardCell } from '../api/types'
import styles from './EvidenceCards.module.css'

/**
 * Source cards: one per external source (agent channel, indicator, job) that
 * has produced a measurable claim. A claim is "this source said this
 * direction on this symbol at this time", extracted by rule from held
 * material and measured like a paper opportunity. Cells across every source
 * are Holm-adjusted together with the skill gate's costs. "Earned" is
 * positive skill that also held out of sample. The panel reports; granting a
 * source any weight stays an operator decision.
 */
export function SourceCards({ symbol }: { symbol?: string }) {
  const { data, isLoading, isError } = useSourceCards(symbol)

  if (isError) return <section className="panel lab-section"><p className="tone-bad">Source cards unavailable. Nothing is inferred.</p></section>
  if (isLoading || !data) return <section className="panel lab-section"><p className="tone-dim">Measuring source cards…</p></section>

  const earned = data.cards.filter((c) => c.earned).length
  const x = data.extraction
  return (
    <section className="panel lab-section" aria-labelledby="source-cards-title">
      <div className="panel-heading">
        <div>
          <h2 id="source-cards-title">Source cards</h2>
          <p>
            Each source measured on its own claims · {data.cards.length} sources · Holm across {data.cells_assessed_together} cells
            · extraction: {x.rows_with_claims} held items yielded claims, {x.rows_without_claims} did not, {x.rows_pending} pending
          </p>
        </div>
        <span className={earned > 0 ? 'tone-good' : 'tone-dim'}>{earned} earned</span>
      </div>
      {data.cards.length === 0 ? (
        <p className="tone-dim" style={{ padding: '0 16px 14px' }}>
          No source has produced a claim yet. A claim needs a tracked symbol and one unambiguous direction in the same clause; reports without a direction are recorded as no-claim.
        </p>
      ) : (
        <div className={styles.grid}>{data.cards.map((c) => <Card key={`${c.source}:${c.source_id}`} card={c} />)}</div>
      )}
      <p className={styles.foot}>{data.note} Costs: {data.costs.source}.</p>
    </section>
  )
}

function Card({ card }: { card: SourceCard }) {
  return (
    <article className={`${styles.card} ${card.earned ? styles.earned : ''}`} aria-label={card.source_id}>
      <div className={styles.head}>
        <span className={styles.id}>{card.source_id}</span>
        <span className={`${styles.standing} ${styles.context}`}>{card.source}</span>
      </div>
      <span className={`${styles.verdict} ${card.earned ? 'tone-good' : 'tone-dim'}`}>
        {card.earned ? `EARNED · ${card.earned_by.join(', ')}` : 'not earned'}
      </span>
      <span className={styles.coverage}>
        {card.claims} claims · {card.claims_measured} measured{card.latest_claim_at ? ` · last ${new Date(card.latest_claim_at).toUTCString().slice(5, 22)}` : ''}
      </span>
      {card.cells.length > 0 && (
        <table className={styles.cells}>
          <thead><tr><th>h</th><th>pol</th><th>n / indep</th><th>skill</th><th>z</th><th>hold-out</th><th>net %</th></tr></thead>
          <tbody>{card.cells.map((c) => <Row key={`${c.horizon_minutes}-${c.polarity}`} c={c} />)}</tbody>
        </table>
      )}
      <p className={styles.next}>{card.next_step}</p>
    </article>
  )
}

function Row({ c }: { c: SourceCardCell }) {
  const pts = (v: number | null) => (v == null ? '—' : `${v * 100 >= 0 ? '+' : ''}${(v * 100).toFixed(1)}`)
  const tone = c.earned ? 'tone-good' : c.detectable ? 'tone-warn' : 'tone-dim'
  return (
    <tr className={tone} title={c.notes.join(' ')}>
      <td>{c.horizon_minutes}m</td>
      <td>{c.polarity === 'as_stated' ? 'as stated' : 'inverted'}</td>
      <td>{c.measured} / {c.independent_pooled}</td>
      <td>{pts(c.skill)}</td>
      <td>{c.z == null ? '—' : c.z.toFixed(2)}</td>
      <td>{pts(c.holdout_skill)}</td>
      <td>{c.mean_net_return_pct == null ? '—' : c.mean_net_return_pct.toFixed(3)}</td>
    </tr>
  )
}
