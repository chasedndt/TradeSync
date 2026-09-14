import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../../api/client'
import styles from './TradeResearch.module.css'

type Summary = { trades: number; resolved: number; net_usdc: number | null; expectancy_usdc: number | null; profit_factor: number | null; median_target_pct: number | null; median_move_pct: number | null; median_holding_minutes: number | null; moves_at_least_3pct: number; measured_moves: number }
type Diagnostics = { methodology_version: string; excluded: number; truncated: boolean; summary: Summary; cohorts: (Summary & { asset: string; timeframe: string })[]; note: string }
type Result = { trades: number; net_usdc: number | null; expectancy_usdc: number | null; profit_factor: number | null; moves_at_least_3pct: number }
type Run = { id: string; symbol: string; style: string; created_at: string; input_sha256: string; version: string; candles: number; from: number; to: number; split_time: number; skipped: Record<string, number>; development: Result; holdout: Result; note: string; assumptions: Record<string, number>; trades: { segment: string; direction: string; entry_time: number; entry: number; stop: number; target: number; exit_reason: string; net_usdc: number; price_move_pct: number }[] }
const fmt = (v: number | null | undefined, suffix = '') => v == null ? '—' : `${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`

export function TradeResearch() {
  const qc = useQueryClient()
  const diagnostics = useQuery({ queryKey: ['trade-diagnostics'], queryFn: () => apiGet<Diagnostics>('/state/trade-research/diagnostics'), refetchInterval: 60000 })
  const runs = useQuery({ queryKey: ['trade-research-runs'], queryFn: () => apiGet<{ runs: Run[] }>('/state/trade-research/runs') })
  const evidence = useQuery({ queryKey: ['trade-research-evidence'], queryFn: () => apiGet<{ sources: { source: string; accepted: number; claims: number; measured: number }[]; scope: string; note: string }>('/state/trade-research/evidence'), refetchInterval: 60000 })
  const [symbol, setSymbol] = useState('BTC-PERP')
  const [style, setStyle] = useState('scalp')
  const [fee, setFee] = useState('4.5')
  const [slip, setSlip] = useState('2')
  const [funding, setFunding] = useState('0.125')
  const submit = useMutation({ mutationFn: () => apiPost<Run>('/state/trade-research/replay', { symbol, style, fee_bps: Number(fee), slippage_bps: Number(slip), funding_bps_hour: Number(funding) }), onSuccess: () => qc.invalidateQueries({ queryKey: ['trade-research-runs'] }) })
  const invalid = [fee, slip, funding].some(v => v.trim() === '' || !Number.isFinite(Number(v)) || Number(v) < 0)
  const d = diagnostics.data
  return (
    <section className={`panel ${styles.panel}`} aria-labelledby="trade-research-title">
      <h3 id="trade-research-title">Trade economics &amp; research</h3>
      <p>Does the setup capture a meaningful price move after costs? Dollar profit alone cannot answer that.</p>
      {diagnostics.isError && <p className="tone-bad">Ledger diagnostics unavailable.</p>}
      {d && <>
        <div className={styles.metrics}>
          <span>Recorded net <strong className={(d.summary.net_usdc ?? 0) < 0 ? 'tone-bad' : ''}>{fmt(d.summary.net_usdc, ' USDC')}</strong></span>
          <span>Per resolved trade <strong>{fmt(d.summary.expectancy_usdc, ' USDC')}</strong></span>
          <span>Median target distance <strong>{fmt(d.summary.median_target_pct, '%')}</strong></span>
          <span>Captured ≥3% moves <strong>{d.summary.moves_at_least_3pct} / {d.summary.measured_moves}</strong></span>
        </div>
        <div className={styles.scroll}><table><thead><tr><th>Market / chart</th><th>Resolved</th><th>Net USDC</th><th>Profit factor</th><th>Median target</th><th>Median actual move</th><th>Median minutes held</th></tr></thead>
          <tbody>{d.cohorts.map(c => <tr key={`${c.asset}-${c.timeframe}`}><td>{c.asset} · {c.timeframe}</td><td>{c.resolved}</td><td>{fmt(c.net_usdc)}</td><td>{fmt(c.profit_factor)}</td><td>{fmt(c.median_target_pct, '%')}</td><td>{fmt(c.median_move_pct, '%')}</td><td>{fmt(c.median_holding_minutes)}</td></tr>)}</tbody></table></div>
        <details><summary>Source and definitions</summary><p>{d.note}</p><p>{d.methodology_version} · {d.excluded} excluded rows · {d.truncated ? 'latest 10,000 trades only' : 'all current-methodology trades within the 10,000-row limit'}. Profit factor = total winning P&amp;L / absolute losing P&amp;L; unavailable with no losses.</p></details>
      </>}
      <h4>Scalp / swing experiments — not promoted strategies</h4>
      <details><summary>Is ingested evidence influencing these trades?</summary>
        {evidence.isError && <p>Evidence coverage unavailable.</p>}
        {evidence.data && <><p>{evidence.data.note}</p><div className={styles.scroll}><table><thead><tr><th>Source</th><th>Accepted intake</th><th>Extracted claims</th><th>Measured claims</th></tr></thead><tbody>{evidence.data.sources.map(s => <tr key={s.source}><td>{s.source}</td><td>{s.accepted}</td><td>{s.claims}</td><td>{s.measured}</td></tr>)}</tbody></table></div><p>{evidence.data.scope} <a href="/regime-lab">Inspect earned evidence cards →</a></p></>}
      </details>
      <p>Scalp: 15-minute entries, up to 3 hours. Swing: 4-hour entries, up to 7 days. Both use closed-candle breakouts with trend and cost gates. No position stacking. Stops win ambiguous candles. Final 30% of the sample is reserved for comparison; repeated tuning against it invalidates that holdout.</p>
      <form className={styles.controls} onSubmit={e => { e.preventDefault(); if (!invalid && !submit.isPending) submit.mutate() }}>
        <label>Market<select value={symbol} onChange={e => setSymbol(e.target.value)}>{['BTC', 'ETH', 'SOL'].map(s => <option key={s} value={`${s}-PERP`}>{s}</option>)}</select></label>
        <label>Style<select value={style} onChange={e => setStyle(e.target.value)}><option value="scalp">Scalp</option><option value="swing">Swing</option></select></label>
        <label>Fee bps / fill<input type="number" min="0" max="100" step="0.1" value={fee} onChange={e => setFee(e.target.value)} /></label>
        <label>Slippage bps / fill<input type="number" min="0" max="100" step="0.1" value={slip} onChange={e => setSlip(e.target.value)} /></label>
        <label>Adverse funding bps / hour<input type="number" min="0" max="10" step="0.001" value={funding} onChange={e => setFunding(e.target.value)} /></label>
        <button className="chip" type="submit" disabled={invalid || submit.isPending}>{submit.isPending ? 'measuring…' : 'Run & save paper replay'}</button>
      </form>
      <p className={styles.note}>1 basis point = 0.01%. Costs are editable research assumptions, not your account’s fee tier. Funding is a stress assumption; historical funding and as-of external evidence are not used by this candidate. Every run retains candles, settings and an input fingerprint. No wallet or live order is involved.</p>
      {submit.isError && <p role="alert" className="tone-bad">{(submit.error as Error).message}</p>}
      {runs.isError && <p className="tone-bad">Saved research unavailable.</p>}
      {runs.data?.runs.length === 0 && <p>No saved replay yet. This is not evidence of profitability.</p>}
      {(runs.data?.runs ?? []).map(r => <details key={r.id} className={styles.run}>
        <summary>{r.symbol} · {r.style} · {new Date(r.created_at).toLocaleString()} · holdout {r.holdout.trades} trades / {fmt(r.holdout.net_usdc, ' USDC')} · unproven</summary>
        <p>Development: {r.development.trades} trades · {fmt(r.development.net_usdc, ' USDC')}. Holdout expectancy: {fmt(r.holdout.expectancy_usdc, ' USDC')} per trade · profit factor {fmt(r.holdout.profit_factor)} · {r.holdout.moves_at_least_3pct} moves ≥3%. {r.candles} closed candles.</p>
        <p>Candle opens UTC: {new Date(r.from * 1000).toISOString()} → {new Date(r.to * 1000).toISOString()}. Holdout starts {new Date(r.split_time * 1000).toISOString()}. Skipped: {Object.entries(r.skipped).map(([k,v]) => `${k.replace(/_/g, ' ')} ${v}`).join(' · ')}.</p>
        <p>{r.note}</p><p>{r.version} · input {r.input_sha256}</p><p>{Object.entries(r.assumptions).map(([k,v]) => `${k.replace(/_/g, ' ')}: ${v}`).join(' · ')}</p>
        <div className={styles.scroll}><table><thead><tr><th>Entry UTC / segment</th><th>Side</th><th>Entry / stop / target</th><th>Exit</th><th>Price move</th><th>Net USDC</th></tr></thead><tbody>{r.trades.map((t,i) => <tr key={i}><td>{new Date(t.entry_time*1000).toISOString().slice(0,16)} · {t.segment}</td><td>{t.direction}</td><td>{fmt(t.entry)} / {fmt(t.stop)} / {fmt(t.target)}</td><td>{t.exit_reason}</td><td>{fmt(t.price_move_pct, '%')}</td><td>{fmt(t.net_usdc)}</td></tr>)}</tbody></table></div>
      </details>)}
    </section>
  )
}
