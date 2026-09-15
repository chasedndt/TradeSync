import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { apiGet, apiPost } from '../../../api/client'
import type { Candidates, RulesCatalog, StyleRules } from './paperTypes'
import { age, duration, exactTime, pct } from './paperFormat'
import styles from './PaperOpenForm.module.css'

const summary = (r: StyleRules): string =>
  `${r.style}: stop ${r.stop_atr} × ATR from ${r.atr_period} closed ${r.atr_interval} candles; target ${r.reward_risk} × the stop distance and at least ${r.min_target_pct}% away; trailing stop from ${r.trail_activate_r} × the stop distance in favour, ${r.trail_atr} × ATR behind the best price; time expiry after ${duration(r.max_hold_s)}.`

/** Pick a fresh opportunity from the tracked universe, a holding style and a notional, then open a paper position. */
export function PaperOpenForm({ entryAllowed, healthy, onOpened }: { entryAllowed: boolean; healthy: boolean; onOpened: () => void }) {
  const candidates = useQuery({ queryKey: ['paper-candidates'], queryFn: () => apiGet<Candidates>('/state/paper-positions/candidates'), refetchInterval: 5000 })
  const rules = useQuery({ queryKey: ['paper-rules'], queryFn: () => apiGet<RulesCatalog>('/state/paper-positions/rules'), staleTime: 3_600_000 })
  const [selected, setSelected] = useState('')
  const [style, setStyle] = useState('intraday')
  const [notional, setNotional] = useState('250')
  const open = useMutation({
    mutationFn: () => apiPost<{ duplicate: boolean }>('/state/paper-positions', { opportunity_id: selected, style, notional: Number(notional) }),
    onSuccess: onOpened,
  })
  const offered = candidates.data?.candidates ?? []
  const cap = rules.data?.common.max_notional_usdc
  const amount = Number(notional)
  const invalid = !offered.some((c) => c.id === selected) || !notional.trim() || !Number.isFinite(amount) || amount <= 0 || cap == null || amount > cap
  const styleNames = rules.data ? Object.keys(rules.data.styles) : [style]
  const chosen = rules.data?.styles[style]
  const data = candidates.data
  const submit = () => {
    if (entryAllowed && !invalid && !open.isPending && window.confirm('Open a paper position from the current order book with the selected rules? Costs and risk gates may refuse this entry. No real order will be sent.')) open.mutate()
  }
  return (
    <>
      <form className={styles.form} onSubmit={(event) => { event.preventDefault(); submit() }}>
        <label>Current opportunity
          <select value={selected} onChange={(event) => { setSelected(event.target.value); open.reset() }}>
            <option value="">Select a fresh opportunity</option>
            {offered.map((c) => (
              <option key={c.id} value={c.id}>{c.symbol} · {c.dir} · {c.timeframe} · {new Date(c.snapshot_ts).toLocaleTimeString()} ({age(c.age_s)} old){c.position_id ? ' · already has a paper position' : ''}</option>
            ))}
          </select>
        </label>
        <label>Holding style
          <select value={style} onChange={(event) => setStyle(event.target.value)}>
            {styleNames.map((name) => {
              const r = rules.data?.styles[name]
              return <option key={name} value={name}>{r ? `${name} · ${r.atr_interval} candles, up to ${duration(r.max_hold_s)}` : name}</option>
            })}
          </select>
        </label>
        <label>Notional USDC<input type="number" min="0.01" max={cap} step="0.01" value={notional} onChange={(event) => setNotional(event.target.value)} /></label>
        <button className="chip" type="submit" disabled={invalid || open.isPending || !healthy || !entryAllowed}>{open.isPending ? 'Checking entry…' : 'Open paper position'}</button>
      </form>
      {chosen && <p className={styles.note}>Rules for {summary(chosen)} Version {rules.data?.version}.</p>}
      {candidates.isLoading && <p className={styles.note}>Loading current opportunities…</p>}
      {candidates.isError && <p role="alert">Opportunities or the tracked universe unavailable: {candidates.error.message}. No candidate substituted.</p>}
      {data && (
        <p className={styles.note}>
          Universe read from the API at {exactTime(data.checked_at)}: {data.universe.join(', ')}.{' '}
          {offered.length === 0
            ? `No eligible opportunity: directional and at most ${data.max_age_s / 60} minutes old. Waiting is valid; no synthetic signal is inserted.`
            : `No fresh opportunity right now for: ${data.symbols_without_candidate.join(', ') || 'none'}.`}
        </p>
      )}
      {rules.data && (
        <details>
          <summary>Paper position rules and costs</summary>
          <p className={styles.note}>Stops use closed-candle ATR; targets are a multiple of the stop distance with a minimum distance; a trailing stop starts after a favourable move and only tightens; every style has a time expiry. These are experimental rules, not validated edges.</p>
          <p className={styles.note}>Fills walk the displayed order book for the position's own size, so spread and depth are measured, not assumed (1 basis point = 0.01%). Fees are Hyperliquid's base taker rate, {pct(rules.data.fees.taker_fee)} per fill, read {rules.data.fees.read_on}. Funding is Hyperliquid's settled hourly funding for the hours a position is open, valued at the recorded oracle price. Planned loss is capped at {rules.data.common.max_planned_risk_usdc} USDC, but gaps can exceed it. Books are checked periodically, not tick by tick.</p>
        </details>
      )}
      {open.isError && <p role="alert" className="tone-bad">{open.error.message}</p>}
      {open.isSuccess && <p role="status">{open.data.duplicate ? 'This opportunity already has a paper position; no duplicate was opened.' : 'Paper position opened. Entry evidence and initial plan are frozen.'}</p>}
    </>
  )
}
