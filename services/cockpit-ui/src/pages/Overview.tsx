import { useSnapshot, useOpportunities, useMarketSnapshots, useMarketStatus, useMacroHeadlines } from '../api/hooks'
import { OpportunityCard } from '../components'
import { AlertTriangle, BarChart3, Globe, Zap, Droplets, Shield, AlertCircle, TrendingUp, TrendingDown, Minus, ExternalLink, RefreshCw } from 'lucide-react'
import type { MarketSnapshotWithMicrostructure } from '../api/types'

// Phase 3C: Execution Conditions Strip Component
function ExecutionConditionsStrip({
  btcSnapshot,
  ethSnapshot
}: {
  btcSnapshot?: MarketSnapshotWithMicrostructure
  ethSnapshot?: MarketSnapshotWithMicrostructure
}) {
  // Helper to get condition badge
  const getConditionBadge = (snapshot?: MarketSnapshotWithMicrostructure, metric: string = 'spread') => {
    if (!snapshot?.microstructure) {
      return { status: 'UNAVAILABLE', color: 'bg-gray-800 text-gray-500', icon: AlertCircle }
    }

    const micro = snapshot.microstructure

    if (metric === 'spread') {
      const spreadOk = micro.spread_bps <= 25
      return {
        status: spreadOk ? 'OK' : 'WIDE',
        color: spreadOk ? 'bg-green-900/30 text-green-400' : 'bg-yellow-900/30 text-yellow-400',
        value: `${micro.spread_bps.toFixed(1)} bps`,
        icon: spreadOk ? Shield : AlertTriangle
      }
    }

    if (metric === 'liquidity') {
      const liqOk = micro.liquidity_score >= 0.5
      return {
        status: liqOk ? 'HEALTHY' : 'THIN',
        color: liqOk ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400',
        value: `${(micro.liquidity_score * 100).toFixed(0)}%`,
        icon: liqOk ? Droplets : AlertCircle
      }
    }

    if (metric === 'slippage') {
      const impact5k = micro.impact_est_bps['5000'] || 0
      const slipOk = impact5k <= 15
      return {
        status: slipOk ? 'LOW' : 'HIGH',
        color: slipOk ? 'bg-green-900/30 text-green-400' : 'bg-orange-900/30 text-orange-400',
        value: `${impact5k.toFixed(1)} bps`,
        icon: slipOk ? Shield : AlertTriangle
      }
    }

    return { status: 'N/A', color: 'bg-gray-800 text-gray-500', icon: AlertCircle }
  }

  const btcSpread = getConditionBadge(btcSnapshot, 'spread')
  const btcLiquidity = getConditionBadge(btcSnapshot, 'liquidity')
  const ethSpread = getConditionBadge(ethSnapshot, 'spread')
  const ethLiquidity = getConditionBadge(ethSnapshot, 'liquidity')

  // Overall execution conditions
  const hasData = btcSnapshot?.microstructure || ethSnapshot?.microstructure
  const allConditionsGood =
    (btcSnapshot?.microstructure?.spread_bps ?? 100) <= 25 &&
    (btcSnapshot?.microstructure?.liquidity_score ?? 0) >= 0.5 &&
    (ethSnapshot?.microstructure?.spread_bps ?? 100) <= 25 &&
    (ethSnapshot?.microstructure?.liquidity_score ?? 0) >= 0.5

  return (
    <div className={`card border-l-4 ${hasData ? (allConditionsGood ? 'border-l-green-500' : 'border-l-yellow-500') : 'border-l-gray-700'}`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2">
          <Shield size={14} className={hasData ? (allConditionsGood ? 'text-green-500' : 'text-yellow-500') : 'text-gray-600'} />
          Execution Conditions
        </h3>
        {hasData ? (
          <span className={`text-[9px] px-2 py-0.5 rounded font-bold ${allConditionsGood ? 'bg-green-900/30 text-green-400' : 'bg-yellow-900/30 text-yellow-400'}`}>
            {allConditionsGood ? 'ALL CLEAR' : 'CAUTION'}
          </span>
        ) : (
          <span className="text-[9px] px-2 py-0.5 rounded font-bold bg-gray-800 text-gray-500">
            UNAVAILABLE
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        {/* BTC Spread */}
        <div className={`${btcSpread.color} rounded p-2`}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-gray-400">BTC Spread</span>
            <btcSpread.icon size={10} />
          </div>
          <div className="font-mono font-bold">{btcSpread.value || btcSpread.status}</div>
        </div>

        {/* BTC Liquidity */}
        <div className={`${btcLiquidity.color} rounded p-2`}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-gray-400">BTC Liq</span>
            <btcLiquidity.icon size={10} />
          </div>
          <div className="font-mono font-bold">{btcLiquidity.value || btcLiquidity.status}</div>
        </div>

        {/* ETH Spread */}
        <div className={`${ethSpread.color} rounded p-2`}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-gray-400">ETH Spread</span>
            <ethSpread.icon size={10} />
          </div>
          <div className="font-mono font-bold">{ethSpread.value || ethSpread.status}</div>
        </div>

        {/* ETH Liquidity */}
        <div className={`${ethLiquidity.color} rounded p-2`}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-gray-400">ETH Liq</span>
            <ethLiquidity.icon size={10} />
          </div>
          <div className="font-mono font-bold">{ethLiquidity.value || ethLiquidity.status}</div>
        </div>
      </div>
    </div>
  )
}

// Phase 3C: Macro Feed Card Component
function MacroFeedCard() {
  const { data: macroData, isLoading, refetch, isFetching } = useMacroHeadlines({ limit: 5 })

  const getSentimentIcon = (sentiment?: string) => {
    if (sentiment === 'bullish') return <TrendingUp size={10} className="text-green-400" />
    if (sentiment === 'bearish') return <TrendingDown size={10} className="text-red-400" />
    return <Minus size={10} className="text-gray-500" />
  }

  const getSentimentColor = (sentiment?: string) => {
    if (sentiment === 'bullish') return 'border-l-green-500'
    if (sentiment === 'bearish') return 'border-l-red-500'
    return 'border-l-gray-600'
  }

  // If no data and loading
  if (isLoading) {
    return (
      <div className="card bg-gray-900/30">
        <h3 className="text-sm font-bold mb-2 text-gray-400 flex items-center gap-2">
          <Globe size={14} />
          Macro Feed
        </h3>
        <div className="flex items-center justify-center py-8">
          <RefreshCw size={20} className="animate-spin text-gray-500" />
        </div>
      </div>
    )
  }

  // If no headlines
  if (!macroData?.headlines?.length) {
    return (
      <div className="card bg-gray-900/30 border-dashed">
        <h3 className="text-sm font-bold mb-2 text-gray-400 flex items-center gap-2">
          <Globe size={14} />
          Macro Feed
        </h3>
        <div className="flex flex-col items-center justify-center py-6 text-center">
          <AlertCircle className="text-gray-700 mb-2" size={24} />
          <p className="text-xs text-gray-600">
            {macroData?.status?.error ? 'Feed error' : 'No headlines available'}
          </p>
          <button
            onClick={() => refetch()}
            className="mt-3 text-[10px] text-blue-500 hover:underline flex items-center gap-1"
          >
            <RefreshCw size={10} />
            RETRY
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="card bg-gray-900/30">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-gray-400 flex items-center gap-2">
          <Globe size={14} className="text-blue-400" />
          Macro Feed
        </h3>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="p-1 hover:bg-gray-800 rounded"
          title="Refresh headlines"
        >
          <RefreshCw size={12} className={`text-gray-500 ${isFetching ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="space-y-2">
        {macroData.headlines.map((headline, idx) => (
          <a
            key={idx}
            href={headline.url}
            target="_blank"
            rel="noopener noreferrer"
            className={`block p-2 bg-gray-900/50 rounded border-l-2 ${getSentimentColor(headline.sentiment)} hover:bg-gray-800/50 transition-colors`}
          >
            <div className="flex items-start gap-2">
              {getSentimentIcon(headline.sentiment)}
              <div className="flex-1 min-w-0">
                <div className="text-[11px] text-gray-300 leading-tight line-clamp-2">
                  {headline.title}
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[9px] text-gray-500">{headline.source}</span>
                  <span className="text-[9px] px-1 py-0.5 rounded bg-gray-800 text-gray-500">
                    {headline.category}
                  </span>
                </div>
              </div>
              <ExternalLink size={10} className="text-gray-600 flex-shrink-0" />
            </div>
          </a>
        ))}
      </div>

      <div className="mt-2 text-[9px] text-gray-600 flex items-center justify-between">
        <span>
          {macroData.status.sources_configured} sources | {macroData.cached ? 'cached' : 'fresh'}
        </span>
        <span>{macroData.status.headlines_cached} total</span>
      </div>
    </div>
  )
}

const regimeColor = (regime?: string) => {
  if (!regime) return 'text-gray-500'
  const r = regime.toLowerCase()
  if (r === 'bullish' || r === 'increasing' || r === 'elevated') return 'text-green-500'
  if (r === 'bearish' || r === 'decreasing' || r === 'subdued') return 'text-red-500'
  return 'text-yellow-500'
}

export function Overview() {
  const { data: snapshot } = useSnapshot()
  const { data: opportunities, isLoading: oppsLoading } = useOpportunities('all', 50)
  const { data: marketData } = useMarketSnapshots()
  const { data: marketStatus } = useMarketStatus()

  const ltfOpps = opportunities?.filter(o => ['15m', '5m', '1m'].includes(o.timeframe)) || []

  // Extract BTC and ETH snapshots for HTF thesis
  const btcSnapshot = marketData?.snapshots?.find(s => s.symbol === 'BTC-PERP')
  const ethSnapshot = marketData?.snapshots?.find(s => s.symbol === 'ETH-PERP')

  // Unique LTF opportunities (one per symbol per direction)
  const curatedLtf = Array.from(new Map(ltfOpps.map(o => [`${o.symbol}-${o.dir}`, o])).values()).slice(0, 6)

  const eventAgeSec = snapshot?.latest_event_ts
    ? Math.floor((Date.now() - new Date(snapshot.latest_event_ts).getTime()) / 1000)
    : null

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Trading Command</h2>
        {eventAgeSec !== null && eventAgeSec > 300 && (
          <div className="flex items-center gap-2 text-red-500 text-sm font-bold animate-pulse">
            <AlertTriangle size={16} />
            DATA STALE ({Math.floor(eventAgeSec / 60)}m ago)
          </div>
        )}
      </div>

      {/* Primary Metrics Strip */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card flex items-center gap-4">
          <div className="p-2 bg-blue-900/20 rounded text-blue-500">
            <Zap size={20} />
          </div>
          <div>
            <div className="text-xs text-gray-400">Flow Rate</div>
            <div className="text-sm font-bold">142 ev/min</div>
          </div>
        </div>
        <div className="card flex items-center gap-4">
          <div className="p-2 bg-green-900/20 rounded text-green-500">
            <BarChart3 size={20} />
          </div>
          <div>
            <div className="text-xs text-gray-400">Execution</div>
            <div className="text-sm font-bold">{snapshot?.execution_gate === 'true' ? 'ARMED' : 'DISARMED'}</div>
          </div>
        </div>
        <div className="card flex items-center gap-4">
          <div className="p-2 bg-purple-900/20 rounded text-purple-500">
            <Globe size={20} />
          </div>
          <div>
            <div className="text-xs text-gray-400">Venues</div>
            <div className="text-sm font-bold flex gap-2">
              <span className={snapshot?.drift_status === 'ok' ? 'text-green-500' : 'text-red-500'}>Drift</span>
              <span className={snapshot?.hl_status === 'ok' ? 'text-green-500' : 'text-red-500'}>HL</span>
            </div>
          </div>
        </div>
        <div className="card flex items-center gap-4">
          <div className="p-2 bg-orange-900/20 rounded text-orange-500">
            <AlertTriangle size={20} />
          </div>
          <div>
            <div className="text-xs text-gray-400">Data Lag</div>
            <div className="text-sm font-bold text-green-500">0.2s</div>
          </div>
        </div>
      </div>

      {/* Phase 3C: Execution Conditions Strip */}
      <ExecutionConditionsStrip btcSnapshot={btcSnapshot as MarketSnapshotWithMicrostructure} ethSnapshot={ethSnapshot as MarketSnapshotWithMicrostructure} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Opportunities */}
        <div className="lg:col-span-2 space-y-6">
          <section>
            <h3 className="text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
              <Zap size={14} className="text-yellow-500" />
              Active Opportunities (LTF)
            </h3>
            {oppsLoading && <div className="text-gray-400">Scanning markets...</div>}
            {curatedLtf.length === 0 && !oppsLoading && (
              <div className="bg-gray-900/50 border border-gray-800 border-dashed rounded-lg p-8 text-center text-gray-500">
                No active signals found in current regime.
              </div>
            )}
            <div className="grid gap-4 md:grid-cols-2">
              {curatedLtf.map((opp) => (
                <OpportunityCard key={opp.id} opportunity={opp} />
              ))}
            </div>
          </section>

          <section>
            <h3 className="text-sm font-medium text-gray-400 mb-3">Recent System Events</h3>
            <div className="card p-0 overflow-hidden">
              <div className="bg-gray-900/50 p-2 text-xs text-gray-500 border-b border-gray-800">
                Telemetry Stream
              </div>
              <div className="p-4 space-y-2 font-mono text-xs">
                <div className="text-blue-400">[03:01:39] Funding convergence detected on ETH-PERP (-0.002% &rarr; -0.001%)</div>
                <div className="text-gray-500">[03:01:35] Drift circuit breaker: health check passed</div>
                <div className="text-yellow-500">[03:01:17] NEW OPPORTUNITY: BTC-PERP 1m SHORT (Strength 84%)</div>
                <div className="text-gray-500">[03:01:05] Synced ingest source: hyperliquid-perp</div>
              </div>
            </div>
          </section>
        </div>

        {/* Right Column: High-Level Context */}
        <div className="space-y-6">
          <div className="card border-l-4 border-l-blue-500">
            <h3 className="text-sm font-bold mb-2">HTF Thesis</h3>
            <div className="space-y-4">
              {btcSnapshot ? (
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-400 text-xs">BTC</span>
                    <span className={`font-bold ${regimeColor(btcSnapshot.regimes?.trend)}`}>
                      {btcSnapshot.regimes?.trend?.toUpperCase() || 'UNKNOWN'}
                    </span>
                  </div>
                  <div className="text-xs text-gray-300 space-y-1">
                    <div className="flex justify-between">
                      <span className="text-gray-500">Funding</span>
                      <span className={regimeColor(btcSnapshot.regimes?.funding)}>
                        {btcSnapshot.regimes?.funding || 'N/A'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">OI</span>
                      <span className={regimeColor(btcSnapshot.regimes?.oi)}>
                        {btcSnapshot.regimes?.oi || 'N/A'}
                      </span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-xs text-gray-500 italic">BTC data unavailable</div>
              )}
              <div className="pt-2 border-t border-gray-800">
                {ethSnapshot ? (
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-gray-400">ETH</span>
                      <span className={`font-bold ${regimeColor(ethSnapshot.regimes?.trend)}`}>
                        {ethSnapshot.regimes?.trend?.toUpperCase() || 'UNKNOWN'}
                      </span>
                    </div>
                    <div className="text-xs text-gray-300 space-y-1">
                      <div className="flex justify-between">
                        <span className="text-gray-500">Funding</span>
                        <span className={regimeColor(ethSnapshot.regimes?.funding)}>
                          {ethSnapshot.regimes?.funding || 'N/A'}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500">OI</span>
                        <span className={regimeColor(ethSnapshot.regimes?.oi)}>
                          {ethSnapshot.regimes?.oi || 'N/A'}
                        </span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-gray-500 italic">ETH data unavailable</div>
                )}
              </div>
            </div>
          </div>

          <MacroFeedCard />

          <div className="card">
            <h3 className="text-sm font-bold mb-3">Market Data Providers</h3>
            <div className="space-y-3">
              {marketStatus?.providers && marketStatus.providers.length > 0 ? (
                marketStatus.providers.map((provider) => (
                  <div key={provider.venue}>
                    <div className="flex justify-between text-[10px] text-gray-500 mb-1">
                      <span className="uppercase">{provider.venue}</span>
                      <span className={provider.enabled ? 'text-green-500' : 'text-red-500'}>
                        {provider.enabled ? 'ENABLED' : 'DISABLED'}
                      </span>
                    </div>
                    <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${provider.enabled ? 'bg-green-500' : 'bg-red-500'}`}
                        style={{ width: provider.enabled ? '100%' : '20%' }}
                      ></div>
                    </div>
                    <div className="text-[9px] text-gray-600 mt-1">
                      Metrics: {provider.metrics?.join(', ') || 'none'}
                    </div>
                  </div>
                ))
              ) : (
                <>
                  <div>
                    <div className="flex justify-between text-[10px] text-gray-500 mb-1">
                      <span>DRIFT</span>
                      <span className={snapshot?.drift_status === 'ok' ? 'text-green-500' : 'text-yellow-500'}>
                        {snapshot?.drift_status === 'ok' ? 'CONNECTED' : 'WAITING'}
                      </span>
                    </div>
                    <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
                      <div className={`h-full ${snapshot?.drift_status === 'ok' ? 'bg-green-500' : 'bg-yellow-500'} w-full`}></div>
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between text-[10px] text-gray-500 mb-1">
                      <span>HYPERLIQUID</span>
                      <span className={snapshot?.hl_status === 'ok' ? 'text-green-500' : 'text-yellow-500'}>
                        {snapshot?.hl_status === 'ok' ? 'CONNECTED' : 'WAITING'}
                      </span>
                    </div>
                    <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
                      <div className={`h-full ${snapshot?.hl_status === 'ok' ? 'bg-green-500' : 'bg-yellow-500'} w-full`}></div>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
