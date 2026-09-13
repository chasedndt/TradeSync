import { Fragment } from 'react'
import { NavLink } from 'react-router-dom'
import { Bank, CurrencyBtc, CurrencyCircleDollar, CurrencyEth, GlobeHemisphereWest, Waves } from '../components/icons'
import type { useContextOverview } from '../api/hooks'
import type { MarketSnapshotWithMicrostructure } from '../api/types'

export function formatUsd(value?: number, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: value > 10_000 ? 1 : digits }).format(value)
}

export function formatCompactUsd(value?: number) {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 2 }).format(value)
}

export function formatPercent(value?: number | null, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`
}

export function formatAge(seconds?: number | null) {
  if (seconds == null || !Number.isFinite(seconds)) return '—'
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  return `${Math.floor(seconds / 3600)}h ago`
}

function AssetIcon({ symbol }: { symbol: string }) {
  if (symbol === 'BTC') return <span className="asset-icon asset-icon--btc"><CurrencyBtc size={18} weight="bold" /></span>
  if (symbol === 'ETH') return <span className="asset-icon asset-icon--eth"><CurrencyEth size={18} weight="fill" /></span>
  return <span className="asset-icon asset-icon--sol"><CurrencyCircleDollar size={18} weight="duotone" /></span>
}

interface ReadinessItemProps { icon: React.ReactNode; label: string; value: string; detail: string; tone: 'good' | 'warn' | 'bad' | 'dim'; to?: string }

export function ReadinessItem({ icon, label, value, detail, tone, to }: ReadinessItemProps) {
  const content = (
    <>
      <span className={`readiness-icon tone-${tone}`}>{icon}</span>
      <div className="readiness-copy">
        <div className="eyebrow">{label}</div>
        <div className={`readiness-value tone-${tone}`}>{value}</div>
        <div className="readiness-detail">{detail}</div>
      </div>
    </>
  )
  return to
    ? <NavLink className="readiness-item readiness-item--link" to={to} title={`Inspect ${label.toLowerCase()}`}>{content}</NavLink>
    : <div className="readiness-item">{content}</div>
}

/** The market table. Clicking a row selects the symbol the chart beside it shows. */
export function MarketPulse({ snapshots, selected, onSelect }: { snapshots: MarketSnapshotWithMicrostructure[]; selected?: string; onSelect: (symbol: string) => void }) {
  const rows = snapshots.filter((snapshot) => snapshot.venue === 'hyperliquid')
  return (
    <section className="panel market-panel market-panel--compact" aria-labelledby="market-pulse-title">
      <div className="panel-heading">
        <div><h2 id="market-pulse-title">Market pulse</h2><p>Hyperliquid perpetuals · click a row to chart it</p></div>
        <div className="panel-actions"><NavLink to="/canvas" className="panel-action">Full canvas →</NavLink></div>
      </div>
      <div className="table-scroll">
        <table className="market-table">
          <thead>
            <tr><th>Market</th><th>Price</th><th>24h</th><th>Funding 8h</th><th>OI Δ 24h</th><th>Spread</th><th>Regime</th><th>Fresh</th></tr>
          </thead>
          <tbody>
            {rows.map((snapshot) => {
              const symbol = snapshot.symbol.replace('-PERP', '')
              const price = snapshot.microstructure?.mid_price ?? snapshot.orderbook?.mid_price
              const oi24 = snapshot.oi?.horizons?.['24h']
              const spread = snapshot.microstructure?.spread_bps ?? snapshot.orderbook?.spread_bps
              const regime = snapshot.regimes?.trend || snapshot.regimes?.market_condition || 'unknown'
              const ageSeconds = (snapshot.snapshot_age_ms ?? snapshot.data_age_ms) / 1000
              const change24h = snapshot.price?.change_24h_pct ?? null
              const isSelected = snapshot.symbol === selected
              return (
                <tr key={snapshot.symbol} className={`market-row--selectable ${isSelected ? 'market-row--selected' : ''}`} onClick={() => onSelect(snapshot.symbol)} aria-selected={isSelected}>
                  <td><div className="market-id"><AssetIcon symbol={symbol} /><div className="market-name"><strong>{symbol}</strong></div></div></td>
                  <td><span className="metric-main">{formatUsd(price, price && price < 1000 ? 2 : 1)}</span></td>
                  <td>{change24h == null ? <span className="metric-main tone-dim">—</span> : <span className={`metric-main ${change24h >= 0 ? 'tone-good' : 'tone-bad'}`}>{formatPercent(change24h)}</span>}</td>
                  <td><span className="metric-main">{snapshot.funding ? `${(snapshot.funding.horizons.h8 * 100).toFixed(4)}%` : '—'}</span></td>
                  <td><span className={`metric-main ${(oi24?.delta_pct ?? 0) >= 0 ? 'tone-good' : 'tone-bad'}`}>{formatPercent(oi24?.delta_pct)}</span></td>
                  <td><span className="metric-main">{spread != null ? `${spread.toFixed(2)} bps` : '—'}</span></td>
                  <td><span className={`regime-badge ${regime.toLowerCase() === 'range' ? 'regime-badge--range' : ''}`}>{regime.toUpperCase()}</span></td>
                  <td><span className={`metric-main ${ageSeconds < 10 ? 'tone-good' : 'tone-warn'}`}>{formatAge(ageSeconds)}</span></td>
                </tr>
              )
            })}
            {!rows.length && <tr><td colSpan={8} className="tone-dim">Waiting for Hyperliquid market snapshots.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function ContextPanel({ context }: { context: ReturnType<typeof useContextOverview>['data'] }) {
  const coin = context?.providers.coingecko
  const llama = context?.providers.defillama
  const fred = context?.providers.fred
  const assets = coin?.data.assets || {}
  return (
    <section className="panel context-panel" aria-labelledby="context-title">
      <div id="context-title" className="context-title">Context only <span>(non-authoritative)</span></div>
      <div className="context-grid">
        <div className="context-block">
          <div className="context-provider"><GlobeHemisphereWest size={18} className="tone-good" weight="duotone" />CoinGecko <span>(spot reference)</span></div>
          <div className="context-assets">
            {['BTC', 'ETH', 'SOL'].map((symbol) => <Fragment key={symbol}><span>{symbol}</span><span>{formatUsd(assets[symbol]?.price_usd, assets[symbol]?.price_usd < 1000 ? 2 : 0)}</span><span className={(assets[symbol]?.change_24h_pct ?? 0) >= 0 ? 'tone-good' : 'tone-bad'}>{formatPercent(assets[symbol]?.change_24h_pct)}</span></Fragment>)}
          </div>
          <div className="context-age">Updated {formatAge(coin?.age_seconds)}</div>
        </div>
        <div className="context-block">
          <div className="context-provider"><Waves size={18} className="tone-info" weight="duotone" />DefiLlama <span>(Hyperliquid TVL)</span></div>
          <div className="context-big">{formatCompactUsd(llama?.data.tvl_usd)}</div>
          <div className="context-age">Updated {formatAge(llama?.age_seconds)}</div>
        </div>
        <div className="context-block">
          <div className="context-provider"><Bank size={18} weight="duotone" />FRED <span>(macro reference)</span></div>
          <div className="context-big tone-dim">{fred?.status === 'healthy' ? 'Configured' : 'Not configured'}</div>
          <div className="context-age">{fred?.status === 'healthy' ? 'official release dates live' : 'free API key required'}</div>
        </div>
      </div>
    </section>
  )
}

interface HealthItemProps { name: string; state: string; detail: string; tone: 'good' | 'warn' | 'bad' | 'dim' }
export function HealthItem({ name, state, detail, tone }: HealthItemProps) {
  return <div className="health-item"><span className="health-name">{name}</span><span className={`health-state tone-${tone}`}>{state}</span><span className="health-latency">{detail}</span></div>
}
