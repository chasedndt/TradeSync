import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiPost } from '../../../api/client'
import type { PaperRowData } from './paperTypes'
import { age, exactTime, price, usdc } from './paperFormat'
import { PaperCosts } from './PaperCosts'
import { PaperEvidence } from './PaperEvidence'
import { PaperExit } from './PaperExit'
import { PaperRules } from './PaperRules'
import styles from './PaperRow.module.css'

/** One managed paper position: levels, the exit that fired, its rules, costs and frozen entry evidence, with an operator close. */
export function PaperRow({ row, refresh }: { row: PaperRowData; refresh: () => void }) {
  const p = row.position_state
  const [inspect, setInspect] = useState(false)
  const close = useMutation({ mutationFn: () => apiPost(`/state/paper-positions/${row.id}/close`, {}), onSuccess: refresh })
  const now = Date.now() / 1000
  const stale = p.status === 'open' && now - p.last_quote_time > 45
  return (
    <article className={styles.position}>
      <h4>{row.symbol} · {p.side} · {p.style} <span>{p.status}</span></h4>
      <p className={styles.times}>Entered {exactTime(p.entry_time)} · last quote {exactTime(p.last_quote_time)} ({age(now - p.last_quote_time)} ago) · {p.observations} quotes checked</p>
      <div className={styles.metrics}>
        <span>Entry fill<strong>{price(p.entry_price)}</strong></span>
        <span>{p.current_stop_rule === 'trailing_stop' ? 'Trailing stop in force' : 'Stop in force'}<strong>{price(p.current_stop ?? p.stop)}</strong></span>
        <span>Target<strong>{price(p.target)}</strong></span>
        <span>Notional<strong>{price(p.notional)} USDC</strong></span>
        <span>{p.status === 'open' ? 'Net if closed at the last book' : 'Net after costs'}<strong>{usdc(p.net_estimate_usdc)}</strong></span>
      </div>
      <PaperExit position={p} />
      {(stale || p.observation_gap) && (
        <p role="status" className="tone-warn">
          {stale ? 'Quote observations are stale. ' : ''}
          {p.observation_gap ? `Observation gap recorded (${Math.round(p.max_observation_gap_s)} seconds): intervening stop/target crossings are unknown; exclude from clean performance evidence.` : 'No current mark or exit can be assumed.'}
        </p>
      )}
      <PaperRules position={p} />
      <PaperCosts id={row.id} position={p} />
      <div className={styles.actions}>
        <button className="chip" onClick={() => setInspect(!inspect)} aria-expanded={inspect}>{inspect ? 'Hide entry evidence' : 'Inspect frozen entry evidence'}</button>
        {p.status === 'open' && (
          <button className="chip" disabled={close.isPending} onClick={() => { if (window.confirm(`Close this ${row.symbol} paper position at the next available fresh quote? No real order will be sent.`)) close.mutate() }}>
            {close.isPending ? 'Closing paper position…' : 'Close paper position'}
          </button>
        )}
      </div>
      {close.isError && <p role="alert" className="tone-bad">{close.error.message}</p>}
      {inspect && <PaperEvidence id={row.id} fingerprint={row.evidence_sha256} />}
    </article>
  )
}
