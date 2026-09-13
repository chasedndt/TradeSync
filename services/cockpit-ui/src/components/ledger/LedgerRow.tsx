import { useState } from 'react'
import { getApiBaseUrl } from '../../api/client'
import type { LabStatus, LedgerRow } from '../../api/strikezoneTypes'
import { directionLabel, humanize, price, toneOf, usd, utcTime } from './format'
import styles from './LedgerTable.module.css'

const STATUS_CLASS: Record<LabStatus, string> = {
  open: styles.open,
  resolving: styles.resolving,
  overdue: styles.overdue,
  resolved: styles.resolved,
  no_trade: styles.noTrade,
}

const cost = (v: number | null) => usd(v == null ? null : -v)

/** One call in the ledger; opening it shows the fills, costs and the charts at the call and at the exit. */
export function LedgerRowView({ row }: { row: LedgerRow }) {
  const [open, setOpen] = useState(false)
  const outcome = row.outcome
  const expandable = Boolean(row.chart_url || outcome)
  const side = row.direction === 'long' ? styles.long : row.direction === 'short' ? styles.short : styles.flat
  const regime = Object.entries(row.regime).map(([tf, r]) => `${tf} ${r}`).join(' · ')

  return (
    <>
      <tr
        className={`${styles.row} ${open ? styles.rowOpen : ''}`}
        onClick={() => expandable && setOpen(!open)}
        style={{ cursor: expandable ? 'pointer' : 'default' }}
        aria-expanded={expandable ? open : undefined}
      >
        <td className={styles.caret}>{expandable ? (open ? '▾' : '▸') : ''}</td>
        <td className={styles.mono}>{utcTime(row.signal_at)}</td>
        <td className={styles.mono}>{row.asset} {row.timeframe}</td>
        <td><span className={`${styles.side} ${side}`}>{directionLabel(row.direction)}</span></td>
        <td className={styles.mono}>{row.confidence == null ? '—' : row.confidence.toFixed(2)}</td>
        <td className={styles.mono}>{price(row.entry_price)}</td>
        <td className={styles.mono}>{price(row.invalidation_price)}</td>
        <td className={styles.mono}>{price(row.target_price)}</td>
        <td className={styles.mono}>{row.planned_reward_risk ?? '—'}</td>
        <td><span className={STATUS_CLASS[row.status]}>{humanize(row.status)}</span></td>
        <td className={styles.mono}>
          {outcome ? `${humanize(outcome.exit_reason)}${outcome.holding_minutes != null ? ` · ${Math.round(outcome.holding_minutes)}m` : ''}` : '—'}
        </td>
        <td className={`${styles.mono} ${toneOf(outcome?.net_pnl_usdc)}`}>{outcome ? usd(outcome.net_pnl_usdc) : '—'}</td>
      </tr>
      {open && (
        <tr className={styles.detail}>
          <td colSpan={12}>
            <div className={styles.detailGrid}>
              <dl className={styles.facts}>
                <dt>regime</dt><dd>{regime || '—'}</dd>
                <dt>expires</dt><dd>{utcTime(row.expiry_at)} UTC</dd>
                {outcome && (
                  <>
                    <dt>fills</dt><dd>{price(outcome.entry_fill_price)} → {price(outcome.exit_fill_price)}</dd>
                    <dt>exit</dt><dd>{utcTime(outcome.exit_at)} UTC · {humanize(outcome.exit_reason)}</dd>
                    <dt>gross</dt><dd className={toneOf(outcome.gross_pnl_usdc)}>{usd(outcome.gross_pnl_usdc)}</dd>
                    <dt>fees</dt><dd>{cost(outcome.fees_usdc)}</dd>
                    <dt>slippage</dt><dd>{cost(outcome.slippage_usdc)}</dd>
                    <dt>funding</dt><dd>{cost(outcome.funding_usdc)}</dd>
                    <dt>net</dt><dd className={toneOf(outcome.net_pnl_usdc)}>{usd(outcome.net_pnl_usdc)}</dd>
                  </>
                )}
              </dl>
              <div className={styles.charts}>
                {row.chart_url ? (
                  <figure>
                    <img src={`${getApiBaseUrl()}${row.chart_url}`} alt={`${row.asset} ${row.timeframe} chart at the call`} loading="lazy" />
                    <figcaption>at the call</figcaption>
                  </figure>
                ) : (
                  <p className={styles.noChart}>The chart at the call has not been copied yet.</p>
                )}
                {outcome?.chart_url && (
                  <figure>
                    <img src={`${getApiBaseUrl()}${outcome.chart_url}`} alt={`${row.asset} ${row.timeframe} chart at the exit`} loading="lazy" />
                    <figcaption>at the exit</figcaption>
                  </figure>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
