import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../../api/client'
import { useOpportunities } from '../../api/hooks/useOpportunities'
import styles from './ManagedPaper.module.css'

type Position = {
  status: string; side: string; style: string; entry_price: number; stop: number; target: number;
  notional: number; expiry: number; last_quote_time: number; observations: number;
  net_estimate_usdc: number | null; fees_usdc?: number; funding_scenario_usdc?: number;
  observation_gap: boolean; max_observation_gap_s: number; exit_reason?: string; exit_price?: number;
}
type Row = { id: string; symbol: string; evidence_sha256: string; position_state: Position }
type Portfolio = { positions: Row[]; worker: { last_tick: number | null; last_error: string | null }; note: string }
type Control = { entries_paused: boolean; reason: string; updated_at: string; note: string }
type Context = { status: string; cutoff?: number; excluded?: number; events?: unknown[]; samples?: unknown[]; coverage?: string; reason?: string; scoring_influence?: boolean }
type Evidence = { entry_evidence?: { external_context?: Record<string, Context> } }
const number = (v: number | null | undefined) => v == null || !Number.isFinite(v) ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: 2 })
const date = (v: number) => new Date(v * 1000).toLocaleString()

function PaperRow({ row, refresh }: { row: Row; refresh: () => void }) {
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
    {p.exit_reason && <p>Exit: {p.exit_reason.replace(/_/g, ' ')} at {number(p.exit_price)}. Simulated, not an exchange fill.</p>}
    {(stale || p.observation_gap) && <p role="status" className="tone-warn">{stale ? 'Quote observations are stale. ' : ''}{p.observation_gap ? `Observation gap recorded (${number(p.max_observation_gap_s)} seconds): intervening stop/target crossings are unknown; exclude from clean performance evidence.` : 'No current mark or exit can be assumed.'}</p>}
    <div className={styles.actions}>
      <button className="chip" onClick={() => setInspect(!inspect)} aria-expanded={inspect}>{inspect ? 'Hide entry evidence' : 'Inspect frozen entry evidence'}</button>
      {p.status === 'open' && <button className="chip" disabled={close.isPending} onClick={() => { if (window.confirm(`Close this ${row.symbol} simulated position at the next available fresh quote? No real order will be sent.`)) close.mutate() }}>{close.isPending ? 'Closing simulation…' : 'Close paper position'}</button>}
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

export function ManagedPaper() {
  const qc = useQueryClient()
  const control = useQuery({ queryKey: ['paper-control'], queryFn: () => apiGet<Control>('/state/paper-control'), refetchInterval: 5000 })
  const [controlReason, setControlReason] = useState('')
  const changeControl = useMutation({ mutationFn: (paused: boolean) => apiPost('/state/paper-control', { entries_paused: paused, reason: controlReason.trim() }), onSuccess: () => qc.invalidateQueries({ queryKey: ['paper-control'] }) })
  const portfolio = useQuery({ queryKey: ['managed-paper'], queryFn: () => apiGet<Portfolio>('/state/paper-positions'), refetchInterval: 15000 })
  const opportunities = useOpportunities('new', 100)
  const [selected, setSelected] = useState('')
  const [style, setStyle] = useState('intraday')
  const [notional, setNotional] = useState('250')
  const refresh = () => { void qc.invalidateQueries({ queryKey: ['managed-paper'] }) }
  const open = useMutation({ mutationFn: () => apiPost<{ duplicate: boolean }>('/state/paper-positions', { opportunity_id: selected, style, notional: Number(notional) }), onSuccess: refresh })
  const now = Date.now()
  const candidates = (opportunities.data ?? []).filter(o => ['BTC-PERP', 'ETH-PERP', 'SOL-PERP'].includes(o.symbol) && ['long', 'short'].includes(o.dir.toLowerCase()) && now - Date.parse(o.snapshot_ts) >= 0 && now - Date.parse(o.snapshot_ts) <= 300000)
  const invalid = !candidates.some(o => o.id === selected) || !notional.trim() || !Number.isFinite(Number(notional)) || Number(notional) <= 0 || Number(notional) > 1000
  const worker = portfolio.data?.worker
  const healthy = worker?.last_tick != null && now / 1000 - worker.last_tick < 60 && !worker.last_error
  const entryAllowed = !control.isError && control.data?.entries_paused === false
  return <section className={`panel ${styles.panel}`} aria-labelledby="managed-paper-title">
    <h3 id="managed-paper-title">Managed paper positions</h3>
    <p>Operator-selected simulations, separate from the historical StrikeZone ledger. No wallet, real order or automatic strategy promotion.</p>
    <p>Observer: {portfolio.isLoading ? 'checking…' : healthy ? 'running' : 'unavailable or stale'}{worker?.last_error ? ` · ${worker.last_error}` : ''}. Maximum three open positions, one per symbol.</p>
    <p>New paper entries: {control.isLoading ? 'checking control…' : control.isError ? 'disabled — control unavailable' : entryAllowed ? 'enabled' : 'paused'}. Existing observations and closes remain available.</p>
    {control.data && <p>Control reason: {control.data.reason} · updated {new Date(control.data.updated_at).toLocaleString()}.</p>}
    <form className={styles.controls} onSubmit={event => { event.preventDefault(); if (controlReason.trim().length >= 5 && control.data && !control.isError && window.confirm(`${entryAllowed ? 'Pause' : 'Resume'} new paper entries? This does not close existing positions or enable real trading.`)) changeControl.mutate(entryAllowed) }}>
      <label>Paper control reason<input maxLength={240} value={controlReason} onChange={event => setControlReason(event.target.value)} placeholder="Reason for pause or resume" /></label>
      <button className="chip" disabled={!control.data || control.isError || changeControl.isPending || controlReason.trim().length < 5}>{entryAllowed ? 'Pause new paper entries' : 'Resume new paper entries'}</button>
    </form>
    {changeControl.isError && <p role="alert">Control change failed: {changeControl.error.message}</p>}
    {changeControl.isSuccess && <p role="status">Paper control updated. No existing position was closed by this action.</p>}
    <form className={styles.controls} onSubmit={e => { e.preventDefault(); if (entryAllowed && !invalid && !open.isPending && window.confirm('Open a simulated position using current quotes and the selected profile? Costs and risk gates may refuse this entry. No real order will be sent.')) open.mutate() }}>
      <label>Current opportunity<select value={selected} onChange={e => { setSelected(e.target.value); open.reset() }}><option value="">Select a fresh opportunity</option>{candidates.map(o => <option key={o.id} value={o.id}>{o.symbol} · {o.dir} · {o.timeframe} · {new Date(o.snapshot_ts).toLocaleTimeString()}</option>)}</select></label>
      <label>Holding style<select value={style} onChange={e => setStyle(e.target.value)}><option value="scalp">Scalp · 15m / up to 3h</option><option value="intraday">Intraday · 1h / up to 24h</option><option value="swing">Swing · 4h / up to 7 days</option></select></label>
      <label>Notional USDC<input type="number" min="0.01" max="1000" step="0.01" value={notional} onChange={e => setNotional(e.target.value)} /></label>
      <button className="chip" type="submit" disabled={invalid || open.isPending || !healthy || !entryAllowed}>{open.isPending ? 'Checking entry…' : 'Open paper position'}</button>
    </form>
    {opportunities.isLoading && <p>Loading current opportunities…</p>}
    {opportunities.isError && <p role="alert">Opportunity feed unavailable. No candidate substituted.</p>}
    {!opportunities.isLoading && !opportunities.isError && candidates.length === 0 && <p>No eligible opportunity within the latest 100 new records: BTC/ETH/SOL, directional, and no older than five minutes. Waiting is valid; no synthetic signal is inserted.</p>}
    <details><summary>Simulation rules and costs</summary><p>Stops use recent closed-candle volatility; target-to-stop distance is 2:1 before costs. Minimum target distances: scalp 0.4%, intraday 0.8%, swing 2%. These are experimental rules, not validated edges.</p><p>Each fill assumes 4.5 basis points fee plus 2 basis points adverse slippage; 1 basis point = 0.01%. Funding is a fixed adverse 0.125 basis points/hour scenario, not settled funding. Entries require fresh tight-spread quotes, sufficient displayed touch size and cost-adjusted risk/reward. Planned loss is capped at 50 USDC, but gaps can exceed it. Observations run about every 15 seconds, not tick-by-tick.</p></details>
    {open.isError && <p role="alert" className="tone-bad">{open.error.message}</p>}
    {open.isSuccess && <p role="status">{open.data.duplicate ? 'This opportunity already has a paper position; no duplicate was opened.' : 'Paper position opened. Entry evidence and initial plan are frozen.'}</p>}
    {portfolio.isError && <p role="alert">Paper portfolio unavailable: {portfolio.error.message}</p>}
    {portfolio.data?.positions.length === 0 && <p>No managed paper positions yet. The empty portfolio is not a zero-return performance result.</p>}
    {portfolio.data?.positions.map(row => <PaperRow key={row.id} row={row} refresh={refresh} />)}
    {portfolio.data && <p className={styles.note}>{portfolio.data.note}</p>}
  </section>
}
