import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../api/client'
import { useReviewQuarantineItem } from '../api/hooks/useQuarantine'
import type { QuarantineItem, QuarantineList } from '../api/types'
import { extractionLine, summarise } from './IntakeSummary'

const PROVENANCE_OPTIONS = [
  { value: 'context_only', label: 'Context only', scoreable: false },
  { value: 'proxy', label: 'Proxy', scoreable: false },
  { value: 'derived', label: 'Derived', scoreable: true },
  { value: 'observed', label: 'Observed', scoreable: true },
]

const SOURCES: { key: string | null; label: string }[] = [
  { key: null, label: 'All' },
  { key: 'tradingview', label: 'Pine alerts' },
  { key: 'discord', label: 'Discord posts' },
  { key: 'chaseos', label: 'Hermes jobs' },
  { key: 'agent_harness', label: 'Harness answers' },
]

function useIntake(source: string | null, pendingOnly: boolean, limit: number) {
  return useQuery({
    queryKey: ['intake', source ?? 'all', pendingOnly, limit],
    queryFn: () => apiGet<QuarantineList>(`/state/quarantine?limit=${limit}&pending_only=${pendingOnly}${source ? `&source=${source}` : ''}`),
    refetchInterval: 30_000,
    retry: 1,
  })
}

/**
 * Knowledge intake: what every Tier B connector sent, read as a person would
 * read it, with what extraction made of each item. Nothing here is evidence.
 * Material sits in quarantine until a human promotes it, and promotion never
 * grants scoring or execution authority.
 */
export function KnowledgeIntake() {
  const [pendingOnly, setPendingOnly] = useState(false)
  const [source, setSource] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const { data, isLoading, isError } = useIntake(source, pendingOnly, 200)

  const items = useMemo(() => {
    const q = query.trim().toLowerCase()
    const all = data?.items ?? []
    if (!q) return all
    return all.filter((i) => {
      const s = summarise(i)
      return `${s.title} ${s.who} ${s.body}`.toLowerCase().includes(q)
    })
  }, [data, query])

  const tally = useMemo(() => {
    const t = { held: items.length, claims: 0, noClaim: 0, unread: 0, refused: 0 }
    for (const i of items) {
      if (!i.accepted) t.refused += 1
      const x = i.extraction
      const n = (x?.rule?.claims ?? 0) + (x?.harness?.claims ?? 0)
      if (!x || (!x.rule && !x.harness)) t.unread += 1
      else if (n > 0) t.claims += 1
      else t.noClaim += 1
    }
    return t
  }, [items])

  return (
    <div className="page">
      <header className="panel-heading" style={{ marginBottom: 16 }}>
        <div>
          <h2>Knowledge intake</h2>
          <p>
            Everything the connectors sent, held as untrusted material with provenance. Each item shows what the rule reader and the
            harness made of it. Nothing here can score, approve or execute; promotion is an operator act.
          </p>
        </div>
      </header>

      <section className="panel" style={{ padding: 16 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
          {SOURCES.map((s) => (
            <button key={s.label} type="button" className={source === s.key ? 'chip chip--active' : 'chip'} onClick={() => setSource(s.key)} aria-pressed={source === s.key}>
              {s.label}
            </button>
          ))}
          <span style={{ width: 1, alignSelf: 'stretch', background: 'var(--border)' }} />
          <button type="button" className={pendingOnly ? 'chip chip--active' : 'chip'} onClick={() => setPendingOnly(!pendingOnly)} aria-pressed={pendingOnly}>
            Awaiting review
          </button>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="filter by text…"
            aria-label="Filter held items"
            style={{ marginLeft: 'auto', background: '#0d1a2a', color: 'var(--text)', border: '1px solid #32445a', borderRadius: 4, padding: '6px 8px', font: '12px var(--font-mono)', minWidth: 180 }}
          />
        </div>

        <div className="metric-sub" style={{ display: 'flex', gap: 16, marginBottom: 12, flexWrap: 'wrap' }}>
          <span>{tally.held} held</span>
          <span className="tone-good">{tally.claims} yielded claims</span>
          <span>{tally.noClaim} read, no claim</span>
          <span>{tally.unread} not yet read</span>
          {tally.refused > 0 && <span className="tone-bad">{tally.refused} refused at intake</span>}
        </div>

        {isError ? (
          <p className="tone-bad">Intake unavailable. The State API did not answer; no submissions are inferred.</p>
        ) : isLoading ? (
          <p className="tone-dim">Loading submissions…</p>
        ) : items.length === 0 ? (
          <p className="tone-dim">Nothing held for this filter. Connectors post here; TradeSync never reaches out to collect from them.</p>
        ) : (
          <div style={{ display: 'grid', gap: 8 }}>
            {items.map((item) => <IntakeRow key={item.id} item={item} />)}
          </div>
        )}

        <p className="market-footnote" style={{ marginTop: 14 }}>
          quarantine → extraction → claims measured on the source cards → operator promotion &nbsp;•&nbsp; refused submissions are kept so an attempted misuse stays visible
        </p>
      </section>
    </div>
  )
}

function IntakeRow({ item }: { item: QuarantineItem }) {
  const [provenance, setProvenance] = useState('context_only')
  const review = useReviewQuarantineItem()
  const s = summarise(item)
  const x = extractionLine(item)
  const decided = Boolean(item.reviewed_by)
  const when = new Date(item.observed_at ?? item.received_at)

  return (
    <details className="panel" style={{ padding: '10px 12px' }}>
      <summary style={{ cursor: 'pointer', display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr) auto', gap: 12, alignItems: 'baseline' }}>
        <span className={`pill ${item.accepted ? 'pill--good' : 'pill--bad'}`}>{item.accepted ? item.source : 'refused'}</span>
        <span style={{ minWidth: 0 }}>
          <strong style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.title}</strong>
          <span className="metric-sub" style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {s.who} · {s.body.split('\n')[0].slice(0, 160)}
          </span>
        </span>
        <span style={{ textAlign: 'right' }}>
          <span className="metric-sub" style={{ display: 'block' }}>{when.toUTCString().slice(5, 22)}</span>
          <span className={`metric-sub ${x.tone}`} style={{ display: 'block' }}>{x.text.slice(0, 70)}</span>
        </span>
      </summary>

      <div style={{ marginTop: 10, display: 'grid', gap: 10 }}>
        <p style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.5, maxHeight: 360, overflowY: 'auto' }}>{s.body}</p>
        {s.extra.length > 0 && <span className="metric-sub">{s.extra.join(' · ')}</span>}
        <span className={`metric-sub ${x.tone}`}>Extraction: {x.text}</span>

        {item.reasons.length > 0 && (
          <div>
            <span className="pipeline-detail-label">Refused because</span>
            <ul>{item.reasons.map((r) => <li key={r.code}><code>{r.code}</code> — {r.detail}</li>)}</ul>
          </div>
        )}

        <details>
          <summary className="metric-sub" style={{ cursor: 'pointer' }}>raw submission · digest {item.content_digest.slice(0, 16)}…</summary>
          <pre style={{ overflowX: 'auto', fontSize: 11, margin: '4px 0 0', maxHeight: 220 }}>{JSON.stringify(item.payload, null, 2)}</pre>
        </details>

        {item.accepted && !item.promoted_to && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <label className="metric-sub" htmlFor={`prov-${item.id}`}>Promote as</label>
            <select id={`prov-${item.id}`} value={provenance} onChange={(e) => setProvenance(e.target.value)}>
              {PROVENANCE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}{o.scoreable ? '' : ' (cannot score)'}</option>)}
            </select>
            <button type="button" className="chip" disabled={review.isPending}
              onClick={() => review.mutate({ id: item.id, reviewedBy: 'operator', promote: true, targetProvenance: provenance })}>
              {review.isPending ? 'Recording…' : 'Review & promote'}
            </button>
            <button type="button" className="chip" disabled={review.isPending}
              onClick={() => review.mutate({ id: item.id, reviewedBy: 'operator', promote: false, targetProvenance: provenance })}>
              Mark reviewed only
            </button>
            {decided && <span className="metric-sub">reviewed by {item.reviewed_by}</span>}
          </div>
        )}
        {item.promoted_to && <span className="pill pill--warn">promoted · {item.promoted_to}</span>}

        {review.data && review.data.blockers.length > 0 && (
          <div className="tone-warn">
            <span className="pipeline-detail-label">Promotion blocked</span>
            <ul>{review.data.blockers.map((b) => <li key={b.code}><code>{b.code}</code> — {b.detail}</li>)}</ul>
          </div>
        )}
      </div>
    </details>
  )
}
