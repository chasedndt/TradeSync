import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { apiGet } from '../../api/client'
import type { EvidenceTimeline as Timeline, TimelineEntry } from '../../api/types'

/**
 * One paper opportunity reconstructed end to end.
 *
 * This is the Phase 4 exit gate made visible: the evidence that produced a
 * call, the exact configuration it was taken under, and what the market did
 * next — without screenshots or memory.
 */
export function EvidenceTimeline({ symbol }: { symbol: string }) {
  const [horizon, setHorizon] = useState(60)
  const { data, isLoading, isError } = useQuery({
    queryKey: ['evidence-timeline', symbol],
    queryFn: () =>
      apiGet<Timeline>(
        `/state/evidence/timeline?symbol=${encodeURIComponent(symbol)}&limit=15`,
      ),
    refetchInterval: 30_000,
  })

  if (isError) {
    return (
      <p className="tone-bad">
        Timeline unavailable. The State API did not answer; no history is inferred.
      </p>
    )
  }
  if (isLoading) return <p className="tone-dim">Loading evidence…</p>
  if (!data?.entries.length) {
    return (
      <p className="tone-dim">
        No paper opportunity recorded for {symbol} yet. Refusals are stored but do
        not appear here — only admitted calls have something to reconstruct.
      </p>
    )
  }

  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <div role="group" aria-label="Outcome horizon" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {[15, 60, 240].map((minutes) => <button key={minutes} type="button"
          className={horizon === minutes ? 'chip chip--active' : 'chip'} aria-pressed={horizon === minutes}
          onClick={() => setHorizon(minutes)}>{minutes}m outcome</button>)}
      </div>
      <p className="metric-sub">Latest {data.entries.length} admitted calls for {symbol}. $ impact below assumes $1,000 unleveraged notional per call; these are independent research observations, not a portfolio simulation.</p>
      {data.entries.map((entry) => (
        <TimelineRow key={entry.opportunity_id} entry={entry} horizon={horizon} />
      ))}
    </div>
  )
}

function TimelineRow({ entry, horizon }: { entry: TimelineEntry; horizon: number }) {
  const measured = entry.outcomes.filter((o) => o.status === 'measured')
  const selected = entry.outcomes.find((o) => o.horizon_minutes === horizon)
  const value = selected?.status === 'measured' && Number.isFinite(selected.signed_return_pct) ? selected.signed_return_pct : null
  return (
    <details className="panel" style={{ padding: 10 }}>
      <summary style={{ cursor: 'pointer', display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
        <span className={entry.direction === 'SHORT' ? 'tone-bad' : 'tone-good'}>
          {entry.direction}
        </span>
        <span className="metric-sub">{new Date(entry.opened_at).toLocaleString()}</span>
        <strong className={value == null ? 'tone-dim' : value > 0 ? 'tone-good' : value < 0 ? 'tone-bad' : 'tone-dim'}>
          {value == null ? `${horizon}m: ${selected?.status ?? 'unavailable'}` : `${horizon}m: ${value >= 0 ? '+' : ''}${value.toFixed(3)}% · ${value >= 0 ? '+' : '-'}$${Math.abs(value * 10).toFixed(2)} gross / $1k`}
        </strong>
        <span className="metric-sub">score {entry.directional_score.toFixed(4)}</span>
        <span className="metric-sub">coverage {entry.coverage_pct.toFixed(1)}%</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {entry.outcomes.map((o) => (
            <span
              key={o.horizon_minutes}
              className={
                o.status !== 'measured'
                  ? 'metric-sub'
                  : (o.signed_return_pct ?? 0) > 0
                    ? 'tone-good'
                    : 'tone-bad'
              }
              style={{ fontSize: 12 }}
            >
              {o.horizon_minutes}m{' '}
              {o.status === 'measured'
                ? `${(o.signed_return_pct ?? 0) >= 0 ? '+' : ''}${(o.signed_return_pct ?? 0).toFixed(3)}%`
                : o.status === 'pending'
                  ? '…'
                  : '—'}
            </span>
          ))}
        </span>
      </summary>

      <div style={{ marginTop: 10, display: 'grid', gap: 8, fontSize: 13 }}>
        <div>
          <span className="pipeline-detail-label">Evidence that produced it</span>
          <ul style={{ margin: '4px 0 0' }}>
            {entry.contributing_features.map((f) => (
              <li key={f.feature_id}>
                <code>{f.feature_id}</code> score {Number(f.score).toFixed(4)}, quality{' '}
                {Number(f.data_quality).toFixed(3)}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <span className="pipeline-detail-label">Configuration it was taken under</span>
          <p style={{ margin: '4px 0 0' }} className="metric-sub">
            catalog {entry.catalog_version} · {entry.catalog_digest?.slice(0, 12)} &nbsp;|&nbsp;
            rulebook {entry.rulebook_version} · {entry.rulebook_digest?.slice(0, 12)}
          </p>
          <p style={{ margin: '2px 0 0' }} className="metric-sub">
            evidence digest {entry.evidence_digest?.slice(0, 24)}
          </p>
        </div>

        <div>
          <span className="pipeline-detail-label">Limits at the time</span>
          <p style={{ margin: '4px 0 0' }} className="metric-sub">
            paper risk {entry.paper_risk_multiplier}× · missing blocks:{' '}
            {entry.missing_blocks.length ? entry.missing_blocks.join(', ') : 'none'}
          </p>
        </div>

        {measured.length > 0 && (
          <div>
            <span className="pipeline-detail-label">What the market did</span>
            <ul style={{ margin: '4px 0 0' }}>
              {measured.map((o) => (
                <li key={o.horizon_minutes}>
                  {o.horizon_minutes}m: signed {(o.signed_return_pct ?? 0).toFixed(4)}% · market
                  moved {(o.forward_return_pct ?? 0).toFixed(4)}% · best{' '}
                  {(o.max_favourable_pct ?? 0).toFixed(3)}% · worst{' '}
                  {(o.max_adverse_pct ?? 0).toFixed(3)}%
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  )
}
