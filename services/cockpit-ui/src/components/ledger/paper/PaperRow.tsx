import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { apiGet, apiPost } from '../../../api/client'
import styles from '../ManagedPaper.module.css'

type Position = {
  status: string; side: string; style: string; entry_price: number; stop: number; target: number;
  notional: number; expiry: number; last_quote_time: number; observations: number;
  net_estimate_usdc: number | null; fees_usdc?: number; funding_scenario_usdc?: number;
  observation_gap: boolean; max_observation_gap_s: number; exit_reason?: string; exit_price?: number;
}
export type Row = { id: string; symbol: string; evidence_sha256: string; position_state: Position }
type Context = { status: string; cutoff?: number; excluded?: number; events?: unknown[]; samples?: unknown[]; coverage?: string; reason?: string; scoring_influence?: boolean }
type Evidence = { entry_evidence?: { external_context?: Record<string, Context> } }
const number = (v: number | null | undefined) => v == null || !Number.isFinite(v) ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: 2 })
const date = (v: number) => new Date(v * 1000).toLocaleString()

export function PaperRow({ row, refresh }: { row: Row; refresh: () => void }) {
  const p = row.position_state
  const [inspect, setInspect] = useState(false)
  const evidence = useQuery({ queryKey: ['paper-evidence', row.id], queryFn: () => apiGet<Evidence>(`/state/paper-positions/${row.id}/evidence`), enabled: inspect })
  const close = useMutation({ mutationFn: () => apiPost(`/state/paper-positions/${row.id}/close`, {}), onSuccess: refresh })
  const stale = p.status === 'open' && Date.now() / 1000 - p.last_quote_time > 45
  return <article className={styles.position}>
    <h4>{row.symbol} · {p.side} · {p.style} <span>{p.status}</span></h4>
    <div className={styles.metrics}>
      <span>Entry / stop / target<strong>{number(p.entry_price)} / {number(p.stop)} / {number(p.target)}</strong></span>
      <span>Notional<strong>{number(p.notional)} USDC</strong></span>
      <span>Estimated net after costs<strong>{number(p.net_estimate_usdc)} USDC</strong></span>
      <span>Fees / funding scenario<strong>{number(p.fees_usdc)} / {number(p.funding_scenario_usdc)} USDC</strong></span>
    </div>
    <p>Last observed: {date(p.last_quote_time)} · {p.observations} observations · time exit: {date(p.expiry)}</p>
    {p.exit_reason && <p>Exit: {p.exit_reason.replace(/_/g, ' ')} at {number(p.exit_price)}. Paper ledger price, not an exchange fill.</p>}
    {(stale || p.observation_gap) && <p role="status" className="tone-warn">{stale ? 'Quote observations are stale. ' : ''}{p.observation_gap ? `Observation gap recorded (${number(p.max_observation_gap_s)} seconds): intervening stop/target crossings are unknown; exclude from clean performance evidence.` : 'No current mark or exit can be assumed.'}</p>}
    <div className={styles.actions}>
      <button className="chip" onClick={() => setInspect(!inspect)} aria-expanded={inspect}>{inspect ? 'Hide entry evidence' : 'Inspect frozen entry evidence'}</button>
      {p.status === 'open' && <button className="chip" disabled={close.isPending} onClick={() => { if (window.confirm(`Close this ${row.symbol} paper position at the next available fresh quote? No real order will be sent.`)) close.mutate() }}>{close.isPending ? 'Closing paper position…' : 'Close paper position'}</button>}
    </div>
    {close.isError && <p role="alert" className="tone-bad">{close.error.message}</p>}
    {inspect && <div className={styles.evidence}>
      <p>Entry fingerprint: {row.evidence_sha256}</p>
      <p>Only evidence captured before entry is frozen. Capturing context does not make it a scored signal.</p>
      {evidence.isLoading && <p>Loading entry evidence…</p>}
      {evidence.isError && <p role="alert">Entry evidence unavailable: {evidence.error.message}</p>}
      {evidence.data != null && <>
        {!evidence.data.entry_evidence?.external_context && <p>No separate context snapshots in this record. Older entries are not backfilled.</p>}
        {Object.entries(evidence.data.entry_evidence?.external_context ?? {}).map(([source, context]) => <div key={source} className={styles.position}>
          <h4>{source === 'bybit_liquidations' ? 'Bybit liquidation receipts' : source === 'hyperliquid_book_history' ? 'Hyperliquid observed book history' : source}</h4>
          <p>Status: {context.status.replace(/_/g, ' ')} · cutoff: {context.cutoff == null ? 'unknown' : date(context.cutoff)}</p>
          <p>Retained observations: {context.events?.length ?? context.samples?.length ?? 'unknown'} · excluded: {context.excluded ?? 'unknown'} · scoring influence: {context.scoring_influence === false ? 'none' : 'not established'}</p>
          {context.reason && <p>Unavailable reason: {context.reason}</p>}
          {context.coverage && <p>{context.coverage}</p>}
        </div>)}
        <details><summary>Raw frozen record</summary><pre>{JSON.stringify(evidence.data, null, 2)}</pre></details>
      </>}
    </div>}
  </article>
}
