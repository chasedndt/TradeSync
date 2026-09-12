import { Fragment } from 'react'
import { NavLink } from 'react-router-dom'
import { MarketChartPanel } from '../components/canvas/MarketChartPanel'
import { EventsStrip } from '../components/EventsStrip'
import {
  Bank,
  BracketsCurly,
  ChartLineDown,
  ChartLineUp,
  CirclesThreePlus,
  CurrencyBtc,
  CurrencyCircleDollar,
  CurrencyEth,
  Gauge,
  GlobeHemisphereWest,
  HardDrives,
  Heartbeat,
  Prohibit,
  Stack,
  Waves,
} from '../components/icons'
import {
  useContextOverview,
  useHealth,
  useMarketSnapshots,
  useOpportunities,
  useSnapshot,
} from '../api/hooks'
import type { MarketSnapshotWithMicrostructure } from '../api/types'

function formatUsd(value?: number, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', maximumFractionDigits: value > 10_000 ? 1 : digits,
  }).format(value)
}

function formatCompactUsd(value?: number) {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 2,
  }).format(value)
}

function formatPercent(value?: number | null, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`
}

function formatAge(seconds?: number | null) {
  if (seconds == null || !Number.isFinite(seconds)) return '—'
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s ago`
  return `${Math.floor(seconds / 60)}m ago`
}

function AssetIcon({ symbol }: { symbol: string }) {
  if (symbol === 'BTC') return <span className="asset-icon asset-icon--btc"><CurrencyBtc size={21} weight="bold" /></span>
  if (symbol === 'ETH') return <span className="asset-icon asset-icon--eth"><CurrencyEth size={21} weight="fill" /></span>
  return <span className="asset-icon asset-icon--sol"><CurrencyCircleDollar size={21} weight="duotone" /></span>
}

interface ReadinessItemProps {
  icon: React.ReactNode
  label: string
  value: string
  detail: string
  tone: 'good' | 'warn' | 'bad' | 'dim'
  to?: string
}

function ReadinessItem({ icon, label, value, detail, tone, to }: ReadinessItemProps) {
  const content = (
    <>
      <span className={`readiness-icon tone-${tone}`}>{icon}</span>
      <div className="readiness-copy">
        <div className="eyebrow">{label}</div>
        <div className={`readiness-value tone-${tone}`}>{value}</div>
        <div className="readiness-detail">{detail}</div>
      </div>
      {to && <span className="readiness-inspect">Inspect →</span>}
    </>
  )
  return to
    ? <NavLink className="readiness-item readiness-item--link" to={to} title={`Inspect ${label.toLowerCase()} dependencies`}>{content}</NavLink>
    : <div className="readiness-item">{content}</div>
}

function MarketPulse({ snapshots }: { snapshots: MarketSnapshotWithMicrostructure[] }) {
  // Every Hyperliquid symbol market-data reports, in its configured order.
  // The list used to be a constant here; it is configured once in compose now.
  const rows = snapshots.filter((snapshot) => snapshot.venue === 'hyperliquid')

  return (
    <section className="panel market-panel" aria-labelledby="market-pulse-title">
      <div className="panel-heading">
        <div><h2 id="market-pulse-title">Market Pulse</h2><p>Hyperliquid Perpetuals (Authoritative)</p></div>
        <div className="panel-actions">
          <NavLink to="/canvas" className="panel-action">Open charts →</NavLink>
          <span>All times UTC</span>
        </div>
      </div>
      <div className="table-scroll">
        <table className="market-table">
          <thead>
            <tr>
              <th>Market</th><th>Price (USD)</th><th>24h Change</th><th>Funding (8h)</th>
              <th>OI Δ (24h)</th><th>Spread</th><th>Liquidity</th><th>Regime</th><th>Freshness</th><th><span className="sr-only">Chart</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((snapshot) => {
              const symbol = snapshot.symbol.replace('-PERP', '')
              const price = snapshot.microstructure?.mid_price ?? snapshot.orderbook?.mid_price
              const oi24 = snapshot.oi?.horizons?.['24h']
              const spread = snapshot.microstructure?.spread_bps ?? snapshot.orderbook?.spread_bps
              const liquidity = snapshot.microstructure?.liquidity_score
              const regime = snapshot.regimes?.trend || snapshot.regimes?.market_condition || 'unknown'
              // Time since this symbol was last observed, the same clock the
              // header's LIVE/STALE uses; metric completeness is a separate fact.
              const ageSeconds = (snapshot.snapshot_age_ms ?? snapshot.data_age_ms) / 1000
              // Hyperliquid publishes prevDayPx beside the mark, so this is a
              // derivation of two authoritative values, not a reconstruction.
              const change24h = snapshot.price?.change_24h_pct ?? null
              return (
                <tr key={snapshot.symbol}>
                  <td><div className="market-id"><AssetIcon symbol={symbol} /><div className="market-name"><strong>{symbol}</strong><span>{snapshot.symbol}</span></div></div></td>
                  <td><span className="metric-main">{formatUsd(price, price && price < 1000 ? 2 : 1)}</span><span className="metric-sub">mark midpoint</span></td>
                  <td>{change24h == null
                    ? <><span className="metric-main tone-dim">—</span><span className="metric-sub">unavailable</span></>
                    : <><span className={`metric-main ${change24h >= 0 ? 'tone-good' : 'tone-bad'}`}>{formatPercent(change24h)}</span><span className="metric-sub">vs prev day</span></>}</td>
                  <td><span className="metric-main">{snapshot.funding ? `${(snapshot.funding.horizons.h8 * 100).toFixed(4)}%` : '—'}</span><span className="metric-sub">{snapshot.funding?.regime?.toUpperCase() || 'UNAVAILABLE'}</span></td>
                  <td><span className={`metric-main ${(oi24?.delta_pct ?? 0) >= 0 ? 'tone-good' : 'tone-bad'}`}>{formatPercent(oi24?.delta_pct)}</span><span className="metric-sub">{formatCompactUsd(oi24?.delta_usd)}</span></td>
                  <td><span className="metric-main tone-good">{spread != null ? `${spread.toFixed(2)} bps` : '—'}</span><span className="metric-sub">{spread != null && spread <= 2 ? 'TIGHT' : 'CHECK'}</span></td>
                  <td><span className={`metric-main ${liquidity != null && liquidity >= .5 ? 'tone-good' : 'tone-warn'}`}>{liquidity != null ? `${Math.round(liquidity * 100)}%` : '—'}</span><span className="metric-sub">{liquidity != null && liquidity >= .7 ? 'GOOD' : 'LIMITED'}</span></td>
                  <td><span className={`regime-badge ${regime.toLowerCase() === 'range' ? 'regime-badge--range' : ''}`}>{regime.toUpperCase()}</span></td>
                  <td><span className={`metric-main ${ageSeconds < 10 ? 'tone-good' : 'tone-warn'}`}>{formatAge(ageSeconds)}</span><span className="metric-sub">{ageSeconds < 10 ? 'LIVE' : 'AGING'}</span></td>
                  <td><NavLink to={`/canvas?symbol=${snapshot.symbol}`} className="panel-action" aria-label={`Open ${symbol} chart`}>Chart →</NavLink></td>
                </tr>
              )
            })}
            {!rows.length && <tr><td colSpan={10} className="tone-dim">Waiting for Hyperliquid market snapshots.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="market-footnote">Source: Hyperliquid API &nbsp; • &nbsp; Perpetuals only &nbsp; • &nbsp; 24h change is derived from the venue&apos;s own previous-day reference, shown as unavailable when Hyperliquid omits it</div>
    </section>
  )
}

function OpportunitiesPanel({ count, loading }: { count: number; loading: boolean }) {
  return (
    <section className="panel" aria-labelledby="paper-opps-title">
      <div className="panel-heading"><div><h2 id="paper-opps-title">Paper Opportunities</h2><p>Review-worthy setups</p></div></div>
      <div className="empty-state">
        <div className="empty-icon"><ChartLineDown size={38} weight="thin" /></div>
        <h3>{loading ? 'Checking scoring output' : count ? `${count} paper setup${count === 1 ? '' : 's'} available` : 'No scored opportunities available'}</h3>
        <p>{count ? 'Open Opportunities to inspect the evidence and paper thesis. Nothing can be sent to a wallet.' : 'Market data is live, but the lean runtime is not currently producing ranked opportunities.'}</p>
        <div className="pipeline-status"><span className="status-dot" />Pipeline status: <strong className="tone-warn">{count ? 'OUTPUT AVAILABLE' : 'PARTIAL'}</strong></div>
      </div>
    </section>
  )
}

function ContextPanel({ context }: { context: ReturnType<typeof useContextOverview>['data'] }) {
  const coin = context?.providers.coingecko
  const llama = context?.providers.defillama
  const fred = context?.providers.fred
  const assets = coin?.data.assets || {}

  return (
    <section className="panel context-panel" aria-labelledby="context-title">
      <div id="context-title" className="context-title">Context Only <span>(Non-Authoritative)</span></div>
      <div className="context-grid">
        <div className="context-block">
          <div className="context-provider"><GlobeHemisphereWest size={20} className="tone-good" weight="duotone" />CoinGecko <span>(Spot Reference)</span></div>
          <div className="context-assets">
            {['BTC', 'ETH', 'SOL'].map((symbol) => <Fragment key={symbol}><span>{symbol}</span><span>{formatUsd(assets[symbol]?.price_usd, assets[symbol]?.price_usd < 1000 ? 2 : 0)}</span><span className={(assets[symbol]?.change_24h_pct ?? 0) >= 0 ? 'tone-good' : 'tone-bad'}>{formatPercent(assets[symbol]?.change_24h_pct)}</span></Fragment>)}
          </div>
          <div className="context-age">Updated {formatAge(coin?.age_seconds)}</div>
        </div>
        <div className="context-block">
          <div className="context-provider"><Waves size={20} className="tone-info" weight="duotone" />DefiLlama <span>(Hyperliquid TVL)</span></div>
          <div className="context-big">{formatCompactUsd(llama?.data.tvl_usd)}</div>
          <div className="context-age">Updated {formatAge(llama?.age_seconds)}</div>
        </div>
        <div className="context-block">
          <div className="context-provider"><Bank size={20} weight="duotone" />FRED <span>(Macro Reference)</span></div>
          <div className="context-big tone-dim">{fred?.status === 'healthy' ? 'Configured' : 'Not configured'}</div>
          <div className="context-age">{fred?.status === 'healthy' ? 'Free macro context enabled' : 'Free API key required to enable'}</div>
        </div>
        <div className="context-block context-note">
          <strong>CONTEXT ONLY</strong> — for situational awareness.<br />
          Authoritative data comes from Hyperliquid.<br />
          No trade decisions are made from these sources.
        </div>
      </div>
    </section>
  )
}

interface HealthItemProps { icon: React.ReactNode; name: string; state: string; detail: string; tone: 'good' | 'warn' | 'bad' | 'dim' }
function HealthItem({ icon, name, state, detail, tone }: HealthItemProps) {
  return <div className="health-item"><span className={`tone-${tone}`}>{icon}</span><span className="health-name">{name}</span><span className={`health-state tone-${tone}`}>{state}</span><span className="health-latency">{detail}</span></div>
}

export function Overview() {
  const { data: marketData, isError: marketError } = useMarketSnapshots()
  const { data: context } = useContextOverview()
  const { data: health, isError: healthError } = useHealth()
  const { data: snapshot } = useSnapshot()
  const { data: opportunities, isLoading: opportunitiesLoading } = useOpportunities('all', 50)
  const snapshots = (marketData?.snapshots || []) as MarketSnapshotWithMicrostructure[]
  // Liveness is judged on how long since each symbol was last observed
  // (snapshot_age_ms), not on the age of the oldest metric inside a snapshot
  // (data_age_ms): the latter is a completeness figure and read a healthy
  // ten-symbol feed as STALE. Falls back to data_age_ms for an older API.
  const observedAge = (item: MarketSnapshotWithMicrostructure) =>
    item.snapshot_age_ms ?? item.data_age_ms
  const freshest = snapshots.length ? Math.min(...snapshots.map(observedAge)) / 1000 : null
  const oldest = snapshots.length ? Math.max(...snapshots.map(observedAge)) / 1000 : null
  // Every symbol is observed each order-book cycle (8s); two cycles missed is stale.
  const marketLive = !marketError && snapshots.length > 0 && (oldest ?? Infinity) < 20
  const marketState = marketError ? 'UNREACHABLE' : snapshots.length === 0 ? 'WAITING' : marketLive ? 'LIVE' : 'STALE'
  const redisHealthy = snapshot ? Object.values(snapshot.stream_lengths || {}).every((value) => value >= 0) : false
  const opportunityCount = opportunities?.length || 0
  const hasSignals = Boolean(snapshot?.latest_signal_ts)

  return (
    <div className="mission-control">
      <section className="panel readiness-strip" aria-label="System readiness">
        <ReadinessItem to="/pipeline" icon={<ChartLineUp size={35} weight="duotone" />} label="Market Data" value={marketState} detail={`Hyperliquid · ${oldest == null ? 'waiting for data' : `oldest symbol update ${formatAge(oldest)}`}`} tone={marketLive ? 'good' : marketError ? 'bad' : 'warn'} />
        <ReadinessItem to="/pipeline" icon={<Heartbeat size={35} weight="duotone" />} label="Intelligence Pipeline" value={hasSignals ? 'ACTIVE' : 'PARTIAL'} detail={hasSignals ? 'Scoring output detected' : 'No current scoring output'} tone={hasSignals ? 'good' : 'warn'} />
        <ReadinessItem to="/pipeline" icon={<Prohibit size={35} weight="bold" />} label="Execution" value="DISABLED" detail="Paper-only · No wallet connected" tone="bad" />
      </section>

      <EventsStrip context={context} />

      <div className="primary-grid">
        <MarketPulse snapshots={snapshots} />
        <MarketChartPanel />
        <OpportunitiesPanel count={opportunityCount} loading={opportunitiesLoading} />
      </div>

      <ContextPanel context={context} />

      <div className="bottom-grid">
        <section className="panel" aria-labelledby="system-health-title">
          <div className="panel-heading"><h2 id="system-health-title">System Health</h2></div>
          <div className="health-grid">
            <HealthItem icon={<HardDrives size={24} weight="duotone" />} name="PostgreSQL" state={health?.postgres ? 'HEALTHY' : 'UNAVAILABLE'} detail={health?.latency_ms != null ? `${health.latency_ms.toFixed(0)}ms` : '—'} tone={health?.postgres ? 'good' : 'bad'} />
            <HealthItem icon={<Stack size={24} weight="duotone" />} name="Redis" state={redisHealthy ? 'HEALTHY' : 'UNAVAILABLE'} detail={redisHealthy ? 'stream checks pass' : '—'} tone={redisHealthy ? 'good' : 'bad'} />
            <HealthItem icon={<PulseIcon />} name="Hyperliquid Market Data" state={marketState} detail={freshest == null ? '—' : `Newest ${formatAge(freshest)} · oldest ${formatAge(oldest)}`} tone={marketLive ? 'good' : marketError ? 'bad' : 'warn'} />
            <HealthItem icon={<BracketsCurly size={24} weight="duotone" />} name="State API" state={!healthError && health ? 'HEALTHY' : 'UNAVAILABLE'} detail={health ? `${health.latency_ms.toFixed(0)}ms DB read` : '—'} tone={!healthError && health ? 'good' : 'bad'} />
            <HealthItem icon={<Gauge size={24} weight="duotone" />} name="Scorer Service" state={hasSignals ? 'OUTPUT SEEN' : 'NO OUTPUT'} detail={hasSignals ? 'signal timestamp present' : 'not measured directly'} tone={hasSignals ? 'good' : 'warn'} />
            <HealthItem icon={<CirclesThreePlus size={24} weight="duotone" />} name="Fusion Engine" state={opportunityCount ? 'OUTPUT SEEN' : 'NO OUTPUT'} detail={opportunityCount ? `${opportunityCount} opportunities` : 'not measured directly'} tone={opportunityCount ? 'good' : 'warn'} />
          </div>
          <div className="health-note">Runtime evidence only. “No output” is not reported as a service outage.</div>
        </section>

        <section className="panel" aria-labelledby="execution-status-title">
          <div className="panel-heading"><h2 id="execution-status-title">Execution Status</h2></div>
          <div className="execution-card">
            <Prohibit size={35} className="tone-bad" weight="bold" />
            <div><h3>DISABLED</h3><strong>Paper-only mode</strong></div>
            <ul className="execution-list"><li>No wallet connected</li><li>No orders can be placed</li></ul>
          </div>
        </section>
      </div>
    </div>
  )
}

function PulseIcon() {
  return <Heartbeat size={24} weight="duotone" />
}
