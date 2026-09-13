import { Fragment, useState } from 'react'
import { NavLink } from 'react-router-dom'
import type { MarketSnapshotWithMicrostructure } from '../../api/types'
import { CaretDown, CaretUp } from '../icons'
import { formatAge, formatPercent, formatPrice } from './format'
import { InlineChart } from './InlineChart'
import styles from './Home.module.css'

const COLUMNS = 9

/** Every tracked market. Clicking a row opens its chart underneath, with timeframe chips. */
export function MarketPulse({ snapshots }: { snapshots: MarketSnapshotWithMicrostructure[] }) {
  const [open, setOpen] = useState<string | null>(null)
  const rows = snapshots.filter((s) => s.venue === 'hyperliquid')

  return (
    <section className="panel market-panel market-panel--compact" aria-labelledby="market-pulse-title">
      <div className="panel-heading">
        <div><h2 id="market-pulse-title">Market Pulse</h2><p>Hyperliquid perpetuals · click a market to open its chart</p></div>
        <NavLink to="/canvas" className="panel-action">Full canvas →</NavLink>
      </div>
      <div className="table-scroll">
        <table className="market-table">
          <thead>
            <tr><th>Market</th><th>Price</th><th>24h</th><th>Funding 8h</th><th>OI Δ 24h</th><th>Spread</th><th>Regime</th><th>Fresh</th><th aria-label="Chart" /></tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const symbol = s.symbol.replace('-PERP', '')
              const price = s.microstructure?.mid_price ?? s.orderbook?.mid_price
              const oi24 = s.oi?.horizons?.['24h']
              const spread = s.microstructure?.spread_bps ?? s.orderbook?.spread_bps
              const regime = s.regimes?.trend || s.regimes?.market_condition || 'unknown'
              const age = (s.snapshot_age_ms ?? s.data_age_ms) / 1000
              const change = s.price?.change_24h_pct ?? null
              const isOpen = open === s.symbol
              return (
                <Fragment key={s.symbol}>
                  <tr
                    className={`${styles.pulseRow} ${isOpen ? styles.pulseRowOpen : ''}`}
                    onClick={() => setOpen(isOpen ? null : s.symbol)}
                    aria-expanded={isOpen}
                  >
                    <td><strong>{symbol}</strong></td>
                    <td><span className="metric-main">{formatPrice(price)}</span></td>
                    <td><span className={`metric-main ${change == null ? 'tone-dim' : change >= 0 ? 'tone-good' : 'tone-bad'}`}>{formatPercent(change)}</span></td>
                    <td><span className="metric-main">{s.funding ? `${(s.funding.horizons.h8 * 100).toFixed(4)}%` : '—'}</span></td>
                    <td><span className={`metric-main ${(oi24?.delta_pct ?? 0) >= 0 ? 'tone-good' : 'tone-bad'}`}>{formatPercent(oi24?.delta_pct)}</span></td>
                    <td><span className="metric-main">{spread != null ? `${spread.toFixed(2)} bps` : '—'}</span></td>
                    <td><span className={`regime-badge ${regime.toLowerCase() === 'range' ? 'regime-badge--range' : ''}`}>{regime.toUpperCase()}</span></td>
                    <td><span className={`metric-main ${age < 10 ? 'tone-good' : 'tone-warn'}`}>{formatAge(age)}</span></td>
                    <td className={styles.caret}>{isOpen ? <CaretUp size={14} /> : <CaretDown size={14} />}</td>
                  </tr>
                  {isOpen && (
                    <tr className={styles.expandRow}>
                      <td colSpan={COLUMNS}><InlineChart symbol={s.symbol} /></td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
            {!rows.length && <tr><td colSpan={COLUMNS} className="tone-dim">Waiting for Hyperliquid market snapshots.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  )
}
