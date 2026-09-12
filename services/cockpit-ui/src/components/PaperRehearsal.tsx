import { useState } from 'react'
import { useOpportunities } from '../api/hooks/useOpportunities'
import { useRehearsals, useRehearse } from '../api/hooks/useRehearsal'
import type { RehearsalRecord } from '../api/types'

/**
 * Preview → refuse → journal, with the execution gate shut.
 *
 * Every result here is a simulation priced from the live mark and spread with
 * the venue's published fees. The endpoint behind it has no path to an
 * execution service; a rehearsal cannot become an order by any sequence of
 * clicks on this page.
 */
export function PaperRehearsal() {
  const { data: opportunities } = useOpportunities('all', 30)
  const { data: journal, isError: journalError } = useRehearsals(25)
  const rehearse = useRehearse()
  const [opportunityId, setOpportunityId] = useState('')
  const [sizeUsd, setSizeUsd] = useState(250)

  const candidates = (opportunities ?? []).filter((o) => o.dir === 'LONG' || o.dir === 'SHORT')
  const last = rehearse.data?.rehearsal

  return (
    <section className="panel" aria-labelledby="rehearsal-title">
      <div className="panel-heading">
        <div>
          <h2 id="rehearsal-title">Paper rehearsal</h2>
          <p>Run the decision path end to end — risk rules, a simulated fill at the live mark, a journal entry — while execution stays disabled.</p>
        </div>
        <span className="tone-dim">SIMULATED</span>
      </div>

      <form
        className="flex flex-col sm:flex-row gap-3 sm:items-end p-5"
        onSubmit={(e) => {
          e.preventDefault()
          if (opportunityId) rehearse.mutate({ opportunity_id: opportunityId, size_usd: sizeUsd })
        }}
      >
        <label className="flex flex-col text-xs text-slate-400 gap-1 flex-1">
          Opportunity
          <select value={opportunityId} onChange={(e) => setOpportunityId(e.target.value)} className="bg-[#0d1928] p-2 rounded text-sm text-slate-100">
            <option value="">Choose a recorded paper opportunity…</option>
            {candidates.map((o) => (
              <option key={o.id} value={o.id}>
                {o.symbol} {o.dir} · quality {Math.round(o.quality)}% · {new Date(o.snapshot_ts).toLocaleTimeString()} · {o.status}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col text-xs text-slate-400 gap-1">
          Size (USD, notional)
          <input type="number" min={1} max={1000000} step={50} value={sizeUsd} onChange={(e) => setSizeUsd(Number(e.target.value))} className="bg-[#0d1928] p-2 rounded text-sm text-slate-100 w-36" />
        </label>
        <button type="submit" className="chip chip--active" disabled={!opportunityId || rehearse.isPending}>
          {rehearse.isPending ? 'Rehearsing…' : 'Rehearse (simulated)'}
        </button>
      </form>

      {rehearse.isError && (
        <p className="tone-bad text-sm px-5">Rehearsal request failed: {String((rehearse.error as Error)?.message ?? 'unknown')}. Nothing was recorded.</p>
      )}
      {last && (
        <div className="px-5 pb-4">
          {rehearse.data?.duplicate && (
            <p className="tone-warn text-xs m-0 mb-2">This opportunity was already rehearsed; showing the existing entry rather than a second fill.</p>
          )}
          <RehearsalRow r={last} expanded />
        </div>
      )}

      <div className="px-5 pb-5">
        <div className="pipeline-detail-label">Journal</div>
        {journalError ? (
          <p className="tone-bad text-sm">Journal unavailable.</p>
        ) : !journal?.rehearsals.length ? (
          <p className="tone-dim text-sm">No rehearsals yet.</p>
        ) : (
          <>
            <p className="metric-sub text-xs">{journal.counts.rehearsed} rehearsed · {journal.counts.refused} refused · {journal.note}</p>
            <div style={{ display: 'grid', gap: 6 }}>
              {journal.rehearsals.map((r) => <RehearsalRow key={r.id} r={r} />)}
            </div>
          </>
        )}
      </div>
    </section>
  )
}

function RehearsalRow({ r, expanded = false }: { r: RehearsalRecord; expanded?: boolean }) {
  const ok = r.status === 'rehearsed'
  return (
    <details className="panel" style={{ padding: 10 }} open={expanded}>
      <summary style={{ cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'center', fontSize: 13 }}>
        <span className={ok ? 'tone-good' : 'tone-bad'}>{ok ? 'REHEARSED' : 'REFUSED'}</span>
        <span className="metric-main" style={{ fontSize: 13 }}>{r.symbol} {r.direction}</span>
        <span className="metric-sub">${r.size_usd.toLocaleString()}</span>
        <span className="metric-sub">{new Date(r.created_at).toLocaleString()}</span>
        {!ok && <span className="metric-sub">{r.risk_verdict.reason_code}</span>}
        {ok && r.fill && <span className="metric-sub" style={{ marginLeft: 'auto' }}>entry cost ${r.fill.entry_cost_usd.toFixed(4)} · breakeven {r.fill.breakeven_move_pct.toFixed(3)}%</span>}
      </summary>
      <div style={{ marginTop: 8, fontSize: 12 }} className="metric-sub">
        <div>{r.risk_verdict.reason}</div>
        {r.fill && (
          <ul style={{ margin: '6px 0 0', paddingLeft: 16 }}>
            <li>mark {r.fill.mark_price} → fill {r.fill.fill_price} (half-spread {r.fill.half_spread_bps} bps)</li>
            <li>fee ${r.fill.fee_usd.toFixed(4)} at {(r.fill.fees.taker_fee * 100).toFixed(3)}% taker · slippage ${r.fill.slippage_usd.toFixed(4)}</li>
            <li>fees from {r.fill.fees.source} (read {r.fill.fees.read_on})</li>
          </ul>
        )}
        <div style={{ marginTop: 6 }}>{r.note}</div>
      </div>
    </details>
  )
}
