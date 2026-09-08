import { useState } from 'react'
import { useQuarantine, useReviewQuarantineItem } from '../api/hooks/useQuarantine'
import type { QuarantineItem } from '../api/types'

const PROVENANCE_OPTIONS = [
  { value: 'context_only', label: 'Context only', scoreable: false },
  { value: 'proxy', label: 'Proxy', scoreable: false },
  { value: 'derived', label: 'Derived', scoreable: true },
  { value: 'observed', label: 'Observed', scoreable: true },
]

/**
 * Knowledge Graph intake — what Tier B connectors have sent, and what an
 * operator decided about it.
 *
 * Nothing shown here is evidence. Material sits in quarantine until a human
 * promotes it, and promotion never grants scoring or execution authority.
 */
export function KnowledgeIntake() {
  const [pendingOnly, setPendingOnly] = useState(false)
  const { data, isLoading, isError } = useQuarantine(pendingOnly)

  return (
    <div className="page">
      <header className="panel-heading" style={{ marginBottom: 16 }}>
        <div>
          <h2>Knowledge intake</h2>
          <p>
            Quarantined submissions from optional connectors. Untrusted until reviewed —
            nothing here can score, approve or execute.
          </p>
        </div>
      </header>

      <section className="panel" style={{ padding: 16 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 14 }}>
          <button
            type="button"
            className={pendingOnly ? 'chip' : 'chip chip--active'}
            onClick={() => setPendingOnly(false)}
            aria-pressed={!pendingOnly}
          >
            All
          </button>
          <button
            type="button"
            className={pendingOnly ? 'chip chip--active' : 'chip'}
            onClick={() => setPendingOnly(true)}
            aria-pressed={pendingOnly}
          >
            Awaiting review
          </button>
          <span className="metric-sub" style={{ marginLeft: 'auto' }}>
            {data ? `${data.items.length} shown` : ''}
          </span>
        </div>

        {isError ? (
          <p className="tone-bad">
            Intake unavailable. The State API did not answer; no submissions are inferred.
          </p>
        ) : isLoading ? (
          <p className="tone-dim">Loading submissions…</p>
        ) : !data?.items.length ? (
          <p className="tone-dim">
            No connector has submitted anything yet. Tier B connectors post here; TradeSync
            never reaches out to collect from them.
          </p>
        ) : (
          <div style={{ display: 'grid', gap: 10 }}>
            {data.items.map((item) => (
              <IntakeRow key={item.id} item={item} />
            ))}
          </div>
        )}

        <p className="market-footnote" style={{ marginTop: 14 }}>
          quarantine → extraction → proposed delta → approved promotion &nbsp;•&nbsp; refused
          submissions are kept so an attempted misuse stays visible
        </p>
      </section>
    </div>
  )
}

function IntakeRow({ item }: { item: QuarantineItem }) {
  const [provenance, setProvenance] = useState('context_only')
  const review = useReviewQuarantineItem()
  const decided = Boolean(item.reviewed_by)

  return (
    <details className="panel" style={{ padding: 12 }}>
      <summary style={{ cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'center' }}>
        <span className={`pill ${item.accepted ? 'pill--good' : 'pill--bad'}`}>
          {item.accepted ? 'accepted' : 'refused'}
        </span>
        <strong>{item.source}</strong>
        <span className="metric-sub">{new Date(item.received_at).toLocaleString()}</span>
        {item.promoted_to && (
          <span className="pill pill--warn">promoted · {item.promoted_to}</span>
        )}
        {!decided && <span className="metric-sub" style={{ marginLeft: 'auto' }}>awaiting review</span>}
      </summary>

      <div style={{ marginTop: 12, display: 'grid', gap: 10 }}>
        {item.reasons.length > 0 && (
          <div>
            <span className="pipeline-detail-label">Refused because</span>
            <ul>
              {item.reasons.map((r) => (
                <li key={r.code}>
                  <code>{r.code}</code> — {r.detail}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <span className="pipeline-detail-label">Submitted content</span>
          <pre
            style={{
              overflowX: 'auto',
              fontSize: 12,
              margin: '4px 0 0',
              maxHeight: 220,
            }}
          >
            {JSON.stringify(item.payload, null, 2)}
          </pre>
        </div>

        {item.accepted && !item.promoted_to && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <label className="metric-sub" htmlFor={`prov-${item.id}`}>
              Promote as
            </label>
            <select
              id={`prov-${item.id}`}
              value={provenance}
              onChange={(e) => setProvenance(e.target.value)}
            >
              {PROVENANCE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                  {o.scoreable ? '' : ' (cannot score)'}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="chip"
              disabled={review.isPending}
              onClick={() =>
                review.mutate({
                  id: item.id,
                  reviewedBy: 'operator',
                  promote: true,
                  targetProvenance: provenance,
                })
              }
            >
              {review.isPending ? 'Recording…' : 'Review & promote'}
            </button>
            <button
              type="button"
              className="chip"
              disabled={review.isPending}
              onClick={() =>
                review.mutate({
                  id: item.id,
                  reviewedBy: 'operator',
                  promote: false,
                  targetProvenance: provenance,
                })
              }
            >
              Mark reviewed only
            </button>
          </div>
        )}

        {review.data && review.data.blockers.length > 0 && (
          <div className="tone-warn">
            <span className="pipeline-detail-label">Promotion blocked</span>
            <ul>
              {review.data.blockers.map((b) => (
                <li key={b.code}>
                  <code>{b.code}</code> — {b.detail}
                </li>
              ))}
            </ul>
          </div>
        )}

        <span className="metric-sub">
          digest {item.content_digest.slice(0, 16)}…
          {item.reviewed_by ? ` · reviewed by ${item.reviewed_by}` : ''}
        </span>
      </div>
    </details>
  )
}
