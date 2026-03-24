import { useState } from 'react'
import {
  TrendingUp,
  Percent,
  BarChart3,
  Flame,
  Activity,
  AlertCircle,
  RefreshCw,
  ChevronDown,
  Droplets,
} from 'lucide-react'
import { useMarketSnapshots, useMarketStatus } from '../api/hooks'
import type { MarketSnapshot, MetricStatus, MarketSnapshotWithMicrostructure } from '../api/types'

// Status badge component with truthful states
function MetricStatusBadge({ status, note }: { status: MetricStatus; note?: string }) {
  const colors: Record<MetricStatus, string> = {
    REAL: 'bg-green-900/50 text-green-400 border-green-700',
    PROXY: 'bg-yellow-900/50 text-yellow-400 border-yellow-700',
    UNAVAILABLE: 'bg-gray-900/50 text-gray-500 border-gray-700',
    STALE: 'bg-red-900/50 text-red-400 border-red-700',
  }

  return (
    <span
      className={`text-[9px] px-1.5 py-0.5 rounded border ${colors[status]}`}
      title={note || status}
    >
      {status}
    </span>
  )
}

// Format large numbers
function formatNumber(n: number, decimals = 2): string {
  if (Math.abs(n) >= 1_000_000_000) return (n / 1_000_000_000).toFixed(decimals) + 'B'
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(decimals) + 'M'
  if (Math.abs(n) >= 1_000) return (n / 1_000).toFixed(decimals) + 'K'
  return n.toFixed(decimals)
}

// Format percentage
function formatPct(n: number, decimals = 2): string {
  return (n * 100).toFixed(decimals) + '%'
}

// Regime badge
function RegimeBadge({ regime }: { regime: string }) {
  const colors: Record<string, string> = {
    extreme_positive: 'bg-red-900/50 text-red-400',
    elevated_positive: 'bg-orange-900/50 text-orange-400',
    neutral: 'bg-gray-800 text-gray-400',
    elevated_negative: 'bg-blue-900/50 text-blue-400',
    extreme_negative: 'bg-cyan-900/50 text-cyan-400',
    build: 'bg-green-900/50 text-green-400',
    unwind: 'bg-red-900/50 text-red-400',
    flat: 'bg-gray-800 text-gray-400',
    high: 'bg-purple-900/50 text-purple-400',
    normal: 'bg-gray-800 text-gray-400',
    low: 'bg-yellow-900/50 text-yellow-400',
  }

  return (
    <span className={`text-xs px-2 py-0.5 rounded ${colors[regime] || 'bg-gray-800 text-gray-400'}`}>
      {regime.replace('_', ' ').toUpperCase()}
    </span>
  )
}

// Funding Panel
function FundingPanel({ snapshot }: { snapshot: MarketSnapshot }) {
  const fundingMetric = snapshot.available_metrics.find((m) => m.metric === 'funding')
  const status = fundingMetric?.status || 'UNAVAILABLE'

  if (status === 'UNAVAILABLE' || !snapshot.funding) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-800 border-dashed flex flex-col items-center justify-center text-center">
        <AlertCircle size={24} className="text-gray-700 mb-2" />
        <p className="text-xs text-gray-600">Funding data unavailable</p>
        <MetricStatusBadge status="UNAVAILABLE" />
      </div>
    )
  }

  const { funding } = snapshot

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <RegimeBadge regime={funding.regime} />
        <MetricStatusBadge status={status} note={fundingMetric?.note} />
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500">Current</div>
          <div className="font-mono">{formatPct(funding.horizons.now, 4)}</div>
        </div>
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500">8h Avg</div>
          <div className="font-mono">{formatPct(funding.horizons.h8, 4)}</div>
        </div>
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500">24h Avg</div>
          <div className="font-mono">{formatPct(funding.horizons.h24, 4)}</div>
        </div>
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500">Annualized</div>
          <div className={`font-mono ${funding.annualized_24h > 0 ? 'text-green-400' : 'text-red-400'}`}>
            {formatPct(funding.annualized_24h)}
          </div>
        </div>
      </div>
    </div>
  )
}

// OI Panel
function OIPanel({ snapshot }: { snapshot: MarketSnapshot }) {
  const oiMetric = snapshot.available_metrics.find((m) => m.metric === 'oi')
  const status = oiMetric?.status || 'UNAVAILABLE'

  if (status === 'UNAVAILABLE' || !snapshot.oi) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-800 border-dashed flex flex-col items-center justify-center text-center">
        <AlertCircle size={24} className="text-gray-700 mb-2" />
        <p className="text-xs text-gray-600">OI data unavailable</p>
        <MetricStatusBadge status="UNAVAILABLE" />
      </div>
    )
  }

  const { oi } = snapshot

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <RegimeBadge regime={oi.regime} />
        <MetricStatusBadge status={status} />
      </div>

      <div className="text-center mb-2">
        <div className="text-2xl font-bold">${formatNumber(oi.current_usd)}</div>
        <div className="text-xs text-gray-500">Total Open Interest</div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        {['5m', '1h', '4h', '24h'].map((window) => {
          const data = oi.horizons[window]
          if (!data) return null
          return (
            <div key={window} className="bg-gray-900/50 rounded p-2">
              <div className="text-gray-500">{window}</div>
              <div className={`font-mono ${data.delta_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {data.delta_pct >= 0 ? '+' : ''}
                {data.delta_pct.toFixed(2)}%
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// Liquidations Panel
function LiquidationsPanel({ snapshot }: { snapshot: MarketSnapshot }) {
  const liqMetric = snapshot.available_metrics.find((m) => m.metric === 'liquidations')
  const status = liqMetric?.status || 'UNAVAILABLE'

  if (status === 'UNAVAILABLE' || !snapshot.liquidations) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-800 border-dashed flex flex-col items-center justify-center text-center">
        <AlertCircle size={24} className="text-gray-700 mb-2" />
        <p className="text-xs text-gray-600">Liquidation feed unavailable</p>
        <MetricStatusBadge status="UNAVAILABLE" />
      </div>
    )
  }

  const { liquidations } = snapshot

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-yellow-500 font-medium">
          {status === 'PROXY' ? 'LIQ PROXY' : 'LIQUIDATIONS'}
        </span>
        <MetricStatusBadge status={status} note={liquidations.source_note} />
      </div>

      {status === 'PROXY' && (
        <div className="text-[10px] text-yellow-600 bg-yellow-900/20 rounded p-2">
          {liquidations.source_note || 'Estimated from OI deltas'}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 text-xs">
        {['1h', '4h', '24h'].map((window) => {
          const data = liquidations.horizons[window]
          if (!data) return null
          return (
            <div key={window} className="bg-gray-900/50 rounded p-2">
              <div className="text-gray-500">{window}</div>
              <div className="flex justify-between">
                <span className="text-green-400">${formatNumber(data.longs_usd, 0)}</span>
                <span className="text-red-400">${formatNumber(data.shorts_usd, 0)}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// Volume Panel
function VolumePanel({ snapshot }: { snapshot: MarketSnapshot }) {
  const volMetric = snapshot.available_metrics.find((m) => m.metric === 'volume')
  const status = volMetric?.status || 'UNAVAILABLE'

  if (status === 'UNAVAILABLE' || !snapshot.volume) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-800 border-dashed flex flex-col items-center justify-center text-center">
        <AlertCircle size={24} className="text-gray-700 mb-2" />
        <p className="text-xs text-gray-600">Volume data unavailable</p>
        <MetricStatusBadge status="UNAVAILABLE" />
      </div>
    )
  }

  const { volume } = snapshot

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <RegimeBadge regime={volume.regime} />
        <MetricStatusBadge status={status} />
      </div>

      <div className="text-center mb-2">
        <div className="text-2xl font-bold">${formatNumber(volume.horizons['24h'] || 0)}</div>
        <div className="text-xs text-gray-500">24h Volume</div>
      </div>

      {volume.cvd && (
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-xs text-gray-500 mb-1">CVD (24h)</div>
          <div className={`font-mono text-sm ${(volume.cvd['24h'] || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {(volume.cvd['24h'] || 0) >= 0 ? '+' : ''}${formatNumber(volume.cvd['24h'] || 0)}
          </div>
          {volume.cvd_method === 'candle_proxy' && (
            <div className="text-[9px] text-yellow-600">PROXY: estimated from candles</div>
          )}
        </div>
      )}
    </div>
  )
}

// Orderbook Panel
function OrderbookPanel({ snapshot }: { snapshot: MarketSnapshot }) {
  const obMetric = snapshot.available_metrics.find((m) => m.metric === 'orderbook')
  const status = obMetric?.status || 'UNAVAILABLE'

  if (status === 'UNAVAILABLE' || !snapshot.orderbook) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-800 border-dashed flex flex-col items-center justify-center text-center">
        <AlertCircle size={24} className="text-gray-700 mb-2" />
        <p className="text-xs text-gray-600">Orderbook data unavailable</p>
        <MetricStatusBadge status="UNAVAILABLE" />
      </div>
    )
  }

  const { orderbook } = snapshot

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium">SPREAD & DEPTH</span>
        <MetricStatusBadge status={status} />
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500">Spread</div>
          <div className="font-mono">{orderbook.spread_bps.toFixed(2)} bps</div>
        </div>
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500">Mid Price</div>
          <div className="font-mono">${orderbook.mid_price.toLocaleString()}</div>
        </div>
      </div>

      <div className="space-y-1">
        <div className="text-xs text-gray-500">Depth (1%)</div>
        <div className="flex gap-1">
          <div className="flex-1 bg-green-900/30 rounded p-1.5 text-xs">
            <div className="text-green-400 font-mono">${formatNumber(orderbook.depth.bid_1pct_usd)}</div>
            <div className="text-[9px] text-gray-500">Bids</div>
          </div>
          <div className="flex-1 bg-red-900/30 rounded p-1.5 text-xs">
            <div className="text-red-400 font-mono">${formatNumber(orderbook.depth.ask_1pct_usd)}</div>
            <div className="text-[9px] text-gray-500">Asks</div>
          </div>
        </div>
        <div className="text-[10px] text-gray-600">
          Imbalance: {(orderbook.imbalance_1pct * 100).toFixed(1)}%
          {orderbook.imbalance_1pct > 0 ? ' (bid heavy)' : ' (ask heavy)'}
        </div>
      </div>
    </div>
  )
}

// Phase 3C: Liquidity Panel
function LiquidityPanel({ snapshot }: { snapshot: MarketSnapshotWithMicrostructure }) {
  const obMetric = snapshot.available_metrics.find((m) => m.metric === 'orderbook')
  const status = obMetric?.status || 'UNAVAILABLE'
  const microstructure = snapshot.microstructure

  if (status === 'UNAVAILABLE' || !microstructure) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-800 border-dashed flex flex-col items-center justify-center text-center">
        <AlertCircle size={24} className="text-gray-700 mb-2" />
        <p className="text-xs text-gray-600">Microstructure data unavailable</p>
        <MetricStatusBadge status="UNAVAILABLE" />
      </div>
    )
  }

  const { spread_bps, depth_usd, impact_est_bps, liquidity_score, book_heatmap } = microstructure

  // Determine liquidity health color
  const liquidityColor = liquidity_score >= 0.7
    ? 'text-green-400'
    : liquidity_score >= 0.4
      ? 'text-yellow-400'
      : 'text-red-400'

  const liquidityBg = liquidity_score >= 0.7
    ? 'bg-green-900/30'
    : liquidity_score >= 0.4
      ? 'bg-yellow-900/30'
      : 'bg-red-900/30'

  // Spread health
  const spreadColor = spread_bps <= 5
    ? 'text-green-400'
    : spread_bps <= 25
      ? 'text-yellow-400'
      : 'text-red-400'

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium">LIQUIDITY & SLIPPAGE</span>
        <MetricStatusBadge status={status} />
      </div>

      {/* Liquidity Score */}
      <div className={`${liquidityBg} rounded-lg p-3 text-center`}>
        <div className="text-[10px] text-gray-500 uppercase mb-1">Liquidity Score</div>
        <div className={`text-2xl font-bold ${liquidityColor}`}>
          {(liquidity_score * 100).toFixed(0)}%
        </div>
        <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden mt-2">
          <div
            className={`h-full ${liquidityColor.replace('text-', 'bg-')}`}
            style={{ width: `${liquidity_score * 100}%` }}
          />
        </div>
      </div>

      {/* Spread Badge */}
      <div className="bg-gray-900/50 rounded p-2">
        <div className="flex justify-between items-center">
          <span className="text-xs text-gray-500">Spread</span>
          <span className={`font-mono text-sm ${spreadColor}`}>
            {spread_bps.toFixed(1)} bps
          </span>
        </div>
      </div>

      {/* Depth Badges */}
      <div className="grid grid-cols-3 gap-1 text-xs">
        {['10bp', '25bp', '50bp'].map((key) => (
          <div key={key} className="bg-gray-900/50 rounded p-1.5 text-center">
            <div className="text-[9px] text-gray-500">{key}</div>
            <div className="font-mono text-[10px]">
              ${formatNumber(depth_usd[key] || 0, 0)}
            </div>
          </div>
        ))}
      </div>

      {/* Slippage Estimates */}
      <div className="space-y-1">
        <div className="text-[10px] text-gray-500 uppercase">Est. Slippage</div>
        <div className="grid grid-cols-3 gap-1 text-xs">
          {['1000', '5000', '10000'].map((size) => {
            const impact = impact_est_bps[size] || 0
            const impactColor = impact <= 5 ? 'text-green-400' : impact <= 15 ? 'text-yellow-400' : 'text-red-400'
            return (
              <div key={size} className="bg-gray-900/50 rounded p-1.5 text-center">
                <div className="text-[9px] text-gray-500">${formatNumber(Number(size), 0)}</div>
                <div className={`font-mono text-[10px] ${impactColor}`}>
                  {impact.toFixed(1)} bps
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Heatmap (simplified bar list) */}
      {book_heatmap && book_heatmap.length > 0 && (
        <div className="space-y-1">
          <div className="text-[10px] text-gray-500 uppercase">Book Heatmap (Top Levels)</div>
          <div className="space-y-0.5 max-h-32 overflow-y-auto">
            {book_heatmap.slice(0, 10).map((level, i) => {
              const maxSize = Math.max(...book_heatmap.map((l) => l.size_usd))
              const widthPct = (level.size_usd / maxSize) * 100
              return (
                <div key={i} className="flex items-center gap-1 text-[9px]">
                  <span className="w-16 text-gray-500 font-mono text-right">
                    ${level.price.toLocaleString()}
                  </span>
                  <div className="flex-1 h-2 bg-gray-800 rounded overflow-hidden">
                    <div
                      className={`h-full ${level.side === 'bid' ? 'bg-green-600' : 'bg-red-600'}`}
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                  <span className={`w-12 text-right font-mono ${level.side === 'bid' ? 'text-green-400' : 'text-red-400'}`}>
                    ${formatNumber(level.size_usd, 0)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// Regime Summary Panel
function RegimeSummary({ snapshot }: { snapshot: MarketSnapshot }) {
  const { regimes } = snapshot

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium">REGIME SUMMARY</span>
        <span
          className={`text-[9px] px-1.5 py-0.5 rounded ${
            regimes.confidence === 'high'
              ? 'bg-green-900/50 text-green-400'
              : regimes.confidence === 'medium'
                ? 'bg-yellow-900/50 text-yellow-400'
                : 'bg-red-900/50 text-red-400'
          }`}
        >
          {regimes.confidence.toUpperCase()} CONF
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-[10px] text-gray-500 mb-1">Funding</div>
          <RegimeBadge regime={regimes.funding} />
        </div>
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-[10px] text-gray-500 mb-1">OI</div>
          <RegimeBadge regime={regimes.oi} />
        </div>
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-[10px] text-gray-500 mb-1">Volume</div>
          <RegimeBadge regime={regimes.volume} />
        </div>
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-[10px] text-gray-500 mb-1">Trend</div>
          <RegimeBadge regime={regimes.trend} />
        </div>
      </div>

      <div className="bg-gray-900/50 rounded p-2">
        <div className="text-[10px] text-gray-500 mb-1">Market Condition</div>
        <div className="text-sm font-bold">
          {regimes.market_condition.replace('_', ' ').toUpperCase()}
        </div>
        {regimes.confidence_note && (
          <div className="text-[9px] text-yellow-600 mt-1">{regimes.confidence_note}</div>
        )}
      </div>
    </div>
  )
}

// Main Market Page
export function Market() {
  const { data, isLoading, error, refetch, isFetching } = useMarketSnapshots()
  const { data: statusData } = useMarketStatus()
  const [selectedVenue, setSelectedVenue] = useState<string>('all')
  const [selectedSymbol, setSelectedSymbol] = useState<string>('BTC-PERP')

  const snapshots = data?.snapshots || []

  // Filter snapshots
  const filteredSnapshots = snapshots.filter((s) => {
    if (selectedVenue !== 'all' && s.venue !== selectedVenue) return false
    if (selectedSymbol !== 'all' && s.symbol !== selectedSymbol) return false
    return true
  })

  // Get unique venues and symbols
  const venues = ['all', ...new Set(snapshots.map((s) => s.venue))]
  const symbols = ['all', ...new Set(snapshots.map((s) => s.symbol))]

  // Get first matching snapshot for detailed view
  const activeSnapshot = filteredSnapshots[0]

  // Check if service is available
  const serviceAvailable = statusData?.providers && statusData.providers.length > 0

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Market Intel</h2>
        <div className="flex items-center gap-3">
          {/* Venue Filter */}
          <div className="relative">
            <select
              value={selectedVenue}
              onChange={(e) => setSelectedVenue(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm appearance-none pr-8"
            >
              {venues.map((v) => (
                <option key={v} value={v}>
                  {v === 'all' ? 'All Venues' : v.charAt(0).toUpperCase() + v.slice(1)}
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500" />
          </div>

          {/* Symbol Filter */}
          <div className="relative">
            <select
              value={selectedSymbol}
              onChange={(e) => setSelectedSymbol(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm appearance-none pr-8"
            >
              {symbols.map((s) => (
                <option key={s} value={s}>
                  {s === 'all' ? 'All Symbols' : s}
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500" />
          </div>

          {/* Refresh */}
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-2 bg-gray-800 rounded hover:bg-gray-700 disabled:opacity-50"
          >
            <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Service Status Banner */}
      {!serviceAvailable && !isLoading && (
        <div className="bg-yellow-900/30 border border-yellow-700/50 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="text-yellow-500" size={20} />
          <div>
            <div className="font-medium text-yellow-400">Market Data Service Unavailable</div>
            <div className="text-xs text-yellow-600">
              The market-data service is not running. Start it with: docker compose -f ops/compose.full.yml up market-data
            </div>
          </div>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <RefreshCw size={24} className="animate-spin text-gray-500" />
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-900/30 border border-red-700/50 rounded-lg p-4">
          <div className="font-medium text-red-400">Error loading market data</div>
          <div className="text-xs text-red-600">{String(error)}</div>
        </div>
      )}

      {/* No Data State */}
      {!isLoading && !error && filteredSnapshots.length === 0 && serviceAvailable && (
        <div className="bg-gray-900/50 border border-gray-800 border-dashed rounded-lg p-8 text-center text-gray-500">
          No market snapshots available. Data should appear within 10 seconds of service startup.
        </div>
      )}

      {/* Main Content */}
      {activeSnapshot && (
        <>
          {/* Data Age Banner */}
          {activeSnapshot.data_age_ms > 30000 && (
            <div className="bg-red-900/30 border border-red-700/50 rounded-lg px-4 py-2 flex items-center gap-2 text-red-400 text-sm">
              <AlertCircle size={16} />
              Data is stale ({Math.floor(activeSnapshot.data_age_ms / 1000)}s old)
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* Funding Regime */}
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-green-900/20 rounded">
                  <Percent size={20} className="text-green-500" />
                </div>
                <div>
                  <h3 className="font-medium">Funding Regime</h3>
                  <p className="text-xs text-gray-500">{activeSnapshot.venue} / {activeSnapshot.symbol}</p>
                </div>
              </div>
              <FundingPanel snapshot={activeSnapshot} />
            </div>

            {/* Open Interest */}
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-blue-900/20 rounded">
                  <BarChart3 size={20} className="text-blue-500" />
                </div>
                <div>
                  <h3 className="font-medium">Open Interest</h3>
                  <p className="text-xs text-gray-500">OI changes and delta tracking</p>
                </div>
              </div>
              <OIPanel snapshot={activeSnapshot} />
            </div>

            {/* Liquidations */}
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-red-900/20 rounded">
                  <Flame size={20} className="text-red-500" />
                </div>
                <div>
                  <h3 className="font-medium">Liquidations</h3>
                  <p className="text-xs text-gray-500">Forced position closures</p>
                </div>
              </div>
              <LiquidationsPanel snapshot={activeSnapshot} />
            </div>

            {/* Volume Profile */}
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-purple-900/20 rounded">
                  <Activity size={20} className="text-purple-500" />
                </div>
                <div>
                  <h3 className="font-medium">Volume Profile</h3>
                  <p className="text-xs text-gray-500">Volume and CVD analysis</p>
                </div>
              </div>
              <VolumePanel snapshot={activeSnapshot} />
            </div>

            {/* Spread & Depth */}
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-orange-900/20 rounded">
                  <TrendingUp size={20} className="text-orange-500" />
                </div>
                <div>
                  <h3 className="font-medium">Spread & Depth</h3>
                  <p className="text-xs text-gray-500">Orderbook liquidity</p>
                </div>
              </div>
              <OrderbookPanel snapshot={activeSnapshot} />
            </div>

            {/* Regime Summary */}
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-cyan-900/20 rounded">
                  <Activity size={20} className="text-cyan-500" />
                </div>
                <div>
                  <h3 className="font-medium">Regime Summary</h3>
                  <p className="text-xs text-gray-500">Aggregated market state</p>
                </div>
              </div>
              <RegimeSummary snapshot={activeSnapshot} />
            </div>

            {/* Phase 3C: Liquidity & Slippage */}
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-teal-900/20 rounded">
                  <Droplets size={20} className="text-teal-500" />
                </div>
                <div>
                  <h3 className="font-medium">Liquidity & Slippage</h3>
                  <p className="text-xs text-gray-500">Microstructure analysis</p>
                </div>
              </div>
              <LiquidityPanel snapshot={activeSnapshot as MarketSnapshotWithMicrostructure} />
            </div>
          </div>

          {/* Source Attribution */}
          <div className="card bg-gray-900/30 text-xs text-gray-500">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-gray-400">Sources: </span>
                {activeSnapshot.sources.map((s, i) => (
                  <span key={i}>
                    {s.provider} ({s.metrics_provided.join(', ')})
                    {i < activeSnapshot.sources.length - 1 ? ', ' : ''}
                  </span>
                ))}
              </div>
              <div className="text-gray-600">
                Updated: {new Date(activeSnapshot.ts).toLocaleTimeString()}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
