import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { apiGet } from '../../api/client'
import styles from './IntradayHorizons.module.css'

type RecordView = { matching_windows: number; non_overlapping_windows: number; share_up: number | null; median_move_pct: number | null }
type Intraday = { symbol: string; closed_candles: number; from: number; last_closed_at: number; last_close: number; ma20: number; note: string; horizons: { hours: number; label: string; state: string; momentum_pct: number; same_state: RecordView; baseline: RecordView }[] }
const pct = (n: number | null) => n == null ? '—' : `${n.toFixed(2)}%`

export function IntradayHorizons({ symbol }: { symbol: string }) {
  const result = useQuery({ queryKey: ['intraday-horizons', symbol], queryFn: () => apiGet<Intraday>(`/state/market/intraday-horizons?symbol=${encodeURIComponent(symbol)}`), refetchInterval: 60000 })
  const data = result.data
  return <section className={`panel ${styles.panel}`} aria-labelledby="intraday-title">
    <h3 id="intraday-title">Trading-day horizons</h3>
    <p>1 hour · 4 hours · 8 hours · 1 day. Measured from hourly candles, separately from the daily-history analysis below.</p>
    {result.isLoading && <p>Loading closed hourly history…</p>}
    {result.isError && <p role="status">Intraday data unavailable: {(result.error as Error).message}</p>}
    {data && <>
      <div className={styles.grid}>{data.horizons.map(h => <article key={h.hours}>
        <h4>{h.label}</h4><p>{h.state}</p>
        <dl><dt>Recent move over this horizon</dt><dd>{pct(h.momentum_pct)}</dd>
          <dt>Median subsequent move: similar state</dt><dd>{pct(h.same_state.median_move_pct)}</dd>
          <dt>Median subsequent move: all states</dt><dd>{pct(h.baseline.median_move_pct)}</dd>
          <dt>Similar-state non-overlapping windows</dt><dd>{h.same_state.non_overlapping_windows}</dd>
        </dl>
        <span>{h.same_state.non_overlapping_windows < 30 ? 'Thin sample — descriptive only' : 'Descriptive record — no demonstrated trading edge'}</span>
      </article>)}</div>
      <details><summary>Source, timing and method</summary><p>{data.note}</p>
        <p>{data.closed_candles} closed candles from {new Date(data.from*1000).toLocaleString()}; latest close {new Date(data.last_closed_at*1000).toLocaleString()}. Last price {data.last_close.toLocaleString()}, 20-hour mean {data.ma20.toLocaleString()}. Thin-sample flag uses 30 windows as a display caution, not a statistical pass threshold.</p>
      </details>
      <Link to={`/canvas?symbol=${encodeURIComponent(symbol)}&interval=1h&view=chart`}>Open hourly Market Canvas →</Link>
    </>}
  </section>
}
