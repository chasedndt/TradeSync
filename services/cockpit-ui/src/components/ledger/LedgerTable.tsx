import { useState } from 'react'
import { useLedger } from '../../api/hooks/useStrikeZone'
import type { LedgerView } from '../../api/strikezoneTypes'
import { LedgerRowView } from './LedgerRow'
import styles from './LedgerTable.module.css'

const VIEWS: { key: LedgerView; label: string }[] = [
  { key: 'trades', label: 'Trades' },
  { key: 'open', label: 'Open' },
  { key: 'resolved', label: 'Resolved' },
  { key: 'no_trade', label: 'No trade' },
  { key: 'all', label: 'Every call' },
]

/** The signal ledger: every call with its levels, status and outcome; a row opens its charts. */
export function LedgerTable({ assets, timeframes }: { assets: string[]; timeframes: string[] }) {
  const [asset, setAsset] = useState('')
  const [timeframe, setTimeframe] = useState('')
  const [view, setView] = useState<LedgerView>('trades')
  const [limit, setLimit] = useState(50)
  const ledger = useLedger({ asset, timeframe, view, limit })
  const rows = ledger.data?.rows ?? []

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h3>Signal ledger</h3>
          <p>newest first · levels as called · outcome after fees, slippage and funding · open a row for its charts</p>
        </div>
      </div>
      <div className={styles.toolbar}>
        {VIEWS.map((v) => (
          <button key={v.key} type="button" className={view === v.key ? 'chip chip--active' : 'chip'} aria-pressed={view === v.key} onClick={() => setView(v.key)}>
            {v.label}
          </button>
        ))}
        <span className={styles.spacer} />
        <select value={asset} onChange={(e) => setAsset(e.target.value)} aria-label="Asset">
          <option value="">all assets</option>
          {assets.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} aria-label="Timeframe">
          <option value="">all timeframes</option>
          {timeframes.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      {ledger.isError && <p className={styles.error}>Ledger unavailable from the state API.</p>}
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th aria-label="open" /><th>called (UTC)</th><th>market</th><th>side</th><th>conf.</th><th>entry</th><th>stop</th>
              <th>target</th><th>R:R</th><th>status</th><th>exit</th><th>net</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => <LedgerRowView key={r.signal_id} row={r} />)}
            {!ledger.isLoading && rows.length === 0 && (
              <tr><td colSpan={12} className={styles.empty}>No calls match. The bridge posts new ledger lines every five minutes.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {rows.length >= limit && limit < 500 && (
        <div className={styles.more}>
          <button type="button" className="chip" onClick={() => setLimit(Math.min(500, limit + 100))}>Show more</button>
        </div>
      )}
    </section>
  )
}
