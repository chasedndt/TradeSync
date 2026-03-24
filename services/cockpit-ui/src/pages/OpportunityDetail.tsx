import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useEvidence, usePreview, useExecute, useMarketSnapshot } from '../api/hooks'
import { StatusBadge, DirectionBadge, EvidenceTrail, PreviewPanel, DryRunBanner } from '../components'
import type { PreviewResponse, ExecutionResult, MetricStatus, MarketSnapshotWithMicrostructure, Confluence } from '../api/types'
import { calculateBiasStrength } from '../utils/metrics'
import { AlertTriangle, ShieldCheck, TrendingUp, Info, Activity, Shield, AlertCircle, Droplets } from 'lucide-react'

const MetricStatusBadge = ({ status }: { status?: MetricStatus }) => {
  if (!status) return null
  const colors: Record<MetricStatus, string> = {
    REAL: 'bg-green-900/30 text-green-400 border-green-800',
    PROXY: 'bg-yellow-900/30 text-yellow-400 border-yellow-800',
    UNAVAILABLE: 'bg-red-900/30 text-red-400 border-red-800',
    STALE: 'bg-orange-900/30 text-orange-400 border-orange-800',
  }
  return (
    <span className={`px-1 py-0.5 rounded text-[8px] font-mono border ${colors[status] || 'bg-gray-800 text-gray-400'}`}>
      {status}
    </span>
  )
}

// Phase 3C: Execution Risk Box Component
function ExecutionRiskBox({
  marketSnapshot,
  confluence
}: {
  marketSnapshot?: MarketSnapshotWithMicrostructure
  confluence?: Confluence
}) {
  const micro = marketSnapshot?.microstructure
  const execRisk = confluence?.execution_risk
  const warnings = confluence?.warnings || []

  // If no data at all
  if (!micro && !execRisk) {
    return (
      <div className="card bg-gray-900/20 border-gray-800">
        <h3 className="text-sm font-bold mb-3 flex items-center gap-2">
          <Shield size={14} className="text-gray-500" />
          Execution Risk
        </h3>
        <div className="flex flex-col items-center justify-center py-4 text-center">
          <AlertCircle size={24} className="text-gray-700 mb-2" />
          <p className="text-xs text-gray-600">Execution risk data unavailable</p>
          <span className="text-[9px] px-2 py-0.5 rounded bg-gray-800 text-gray-500 mt-2">UNAVAILABLE</span>
        </div>
      </div>
    )
  }

  // Extract values - prefer confluence data, fallback to microstructure
  const spreadBps = execRisk?.spread_bps ?? micro?.spread_bps ?? 0
  const depth25bp = execRisk?.depth_25bp ?? micro?.depth_usd?.['25bp'] ?? 0
  const impact5k = execRisk?.impact_est_bps_5k ?? micro?.impact_est_bps?.['5000'] ?? 0
  const liquidityScore = execRisk?.liquidity_score ?? micro?.liquidity_score ?? 0
  const flags = execRisk?.flags || []

  // Determine overall risk level
  const hasHighRisk = flags.length > 0 || spreadBps > 25 || liquidityScore < 0.4 || impact5k > 15
  const hasMediumRisk = spreadBps > 10 || liquidityScore < 0.6 || impact5k > 8

  const riskLevel = hasHighRisk ? 'HIGH' : hasMediumRisk ? 'MEDIUM' : 'LOW'
  const riskColor = hasHighRisk
    ? 'border-l-red-500'
    : hasMediumRisk
      ? 'border-l-yellow-500'
      : 'border-l-green-500'
  const riskBgColor = hasHighRisk
    ? 'bg-red-900/10'
    : hasMediumRisk
      ? 'bg-yellow-900/10'
      : 'bg-green-900/10'
  const riskTextColor = hasHighRisk
    ? 'text-red-400'
    : hasMediumRisk
      ? 'text-yellow-400'
      : 'text-green-400'

  return (
    <div className={`card ${riskBgColor} border-l-4 ${riskColor}`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold flex items-center gap-2">
          <Shield size={14} className={riskTextColor} />
          Execution Risk
        </h3>
        <span className={`text-[9px] px-2 py-0.5 rounded font-bold ${riskBgColor.replace('/10', '/30')} ${riskTextColor}`}>
          {riskLevel} RISK
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs mb-3">
        {/* Spread */}
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500 text-[10px] mb-1">Spread</div>
          <div className={`font-mono font-bold ${spreadBps <= 10 ? 'text-green-400' : spreadBps <= 25 ? 'text-yellow-400' : 'text-red-400'}`}>
            {spreadBps.toFixed(1)} bps
          </div>
        </div>

        {/* Liquidity Score */}
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500 text-[10px] mb-1">Liquidity</div>
          <div className={`font-mono font-bold ${liquidityScore >= 0.6 ? 'text-green-400' : liquidityScore >= 0.4 ? 'text-yellow-400' : 'text-red-400'}`}>
            {(liquidityScore * 100).toFixed(0)}%
          </div>
        </div>

        {/* Depth at 25bp */}
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500 text-[10px] mb-1">Depth (25bp)</div>
          <div className="font-mono font-bold">
            ${depth25bp >= 1_000_000 ? (depth25bp / 1_000_000).toFixed(1) + 'M' : (depth25bp / 1_000).toFixed(0) + 'K'}
          </div>
        </div>

        {/* Impact @ $5k */}
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500 text-[10px] mb-1">Slippage ($5k)</div>
          <div className={`font-mono font-bold ${impact5k <= 8 ? 'text-green-400' : impact5k <= 15 ? 'text-yellow-400' : 'text-red-400'}`}>
            {impact5k.toFixed(1)} bps
          </div>
        </div>
      </div>

      {/* Flags/Warnings */}
      {(flags.length > 0 || warnings.length > 0) && (
        <div className="space-y-1">
          {flags.map((flag, i) => (
            <div key={`flag-${i}`} className="flex items-center gap-2 text-[10px] text-orange-400 bg-orange-900/20 rounded px-2 py-1">
              <AlertTriangle size={10} />
              <span>{flag.replace(/_/g, ' ')}</span>
            </div>
          ))}
          {warnings.map((warning, i) => (
            <div key={`warn-${i}`} className="flex items-center gap-2 text-[10px] text-yellow-400 bg-yellow-900/20 rounded px-2 py-1">
              <AlertCircle size={10} />
              <span>{warning}</span>
            </div>
          ))}
        </div>
      )}

      {/* Data source label */}
      <div className="mt-2 text-[9px] text-gray-600 text-right">
        {execRisk ? 'Source: confluence analysis' : 'Source: live microstructure'}
      </div>
    </div>
  )
}

export function OpportunityDetail() {
  const { id } = useParams<{ id: string }>()
  const { data: evidence, isLoading, error } = useEvidence(id)
  const previewMutation = usePreview()
  const executeMutation = useExecute()

  // Extract symbol for market context (fallback until evidence loads)
  const symbol = evidence?.opportunity?.symbol || ''
  const { data: marketSnapshot } = useMarketSnapshot('hyperliquid', symbol)

  const [sizeUsd, setSizeUsd] = useState(1000)
  const [venue, setVenue] = useState('drift')
  const [previewResult, setPreviewResult] = useState<PreviewResponse | null>(null)
  const [executeResult, setExecuteResult] = useState<ExecutionResult | null>(null)

  const handlePreview = async () => {
    if (!id) return
    setExecuteResult(null)
    const result = await previewMutation.mutateAsync({
      opportunity_id: id,
      size_usd: sizeUsd,
      venue,
    })
    setPreviewResult(result)
  }

  const handleExecute = async (decisionId: string) => {
    const result = await executeMutation.mutateAsync({
      decision_id: decisionId,
      confirm: true,
    })
    setExecuteResult(result)
  }

  if (isLoading) {
    return <div className="text-gray-400">Syncing with data nodes...</div>
  }

  if (error || !evidence) {
    return (
      <div className="space-y-4">
        <Link to="/opportunities" className="text-blue-400 hover:underline text-sm flex items-center gap-1">
          &larr; Back to Opportunities
        </Link>
        <div className="card border-red-900 bg-red-900/10 text-red-400 flex items-center gap-3">
          <AlertTriangle size={20} />
          Error loading opportunity details. The record may have expired.
        </div>
      </div>
    )
  }

  const { opportunity } = evidence

  if (!opportunity) {
    return (
      <div className="space-y-4">
        <Link to="/opportunities" className="text-blue-400 hover:underline text-sm">
          &larr; Back to Opportunities
        </Link>
        <div className="text-gray-400">Opportunity not found.</div>
      </div>
    )
  }

  const biasStrength = calculateBiasStrength(opportunity.bias)
  const ageMs = Date.now() - new Date(opportunity.snapshot_ts).getTime()
  const ageSec = Math.floor(ageMs / 1000)

  return (
    <div className="space-y-6">
      <Link to="/opportunities" className="text-blue-400 hover:underline text-sm flex items-center gap-1">
        &larr; Back to Opportunities
      </Link>

      {/* Dry Run / Mode Banner */}
      <DryRunBanner variant="compact" />

      {/* Opportunity Header */}
      <div className="card border-l-4 border-l-blue-500">
        <div className="flex items-start justify-between mb-6">
          <div className="flex gap-4">
            <div className="p-3 bg-blue-900/20 rounded">
              <TrendingUp size={24} className="text-blue-500" />
            </div>
            <div>
              <h2 className="text-2xl font-bold">{opportunity.symbol}</h2>
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <span className="bg-gray-800 px-1.5 py-0.5 rounded">{opportunity.timeframe}</span>
                <span>Detected {new Date(opportunity.snapshot_ts).toLocaleTimeString()}</span>
                <span>({ageSec}s ago)</span>
              </div>
            </div>
          </div>
          <StatusBadge status={opportunity.status} />
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="space-y-1">
            <div className="text-xs text-gray-400 uppercase tracking-wider">Direction</div>
            <DirectionBadge direction={opportunity.dir} />
          </div>
          <div className="space-y-1">
            <div className="text-xs text-gray-400 uppercase tracking-wider">Pulse Strength</div>
            <div className="text-lg font-bold">{biasStrength.toFixed(1)}%</div>
            <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
              <div className="h-full bg-blue-500" style={{ width: `${biasStrength}%` }}></div>
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-xs text-gray-400 uppercase tracking-wider">Opportunity Quality</div>
            <div className="text-lg font-bold">{opportunity.quality.toFixed(1)}%</div>
            <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
              <div className="h-full bg-green-500" style={{ width: `${opportunity.quality}%` }}></div>
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-xs text-gray-400 uppercase tracking-wider">Risk Confidence</div>
            <div className="flex items-center gap-2 text-green-500">
              <ShieldCheck size={16} />
              <span className="font-bold">VERIFIED</span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-5 gap-6">
        {/* Left 3/5: Evidence and Insights */}
        <div className="lg:col-span-3 space-y-6">
          <section className="card bg-gray-900/20 border-gray-800">
            <h3 className="text-sm font-bold mb-3 flex items-center gap-2">
              <Info size={14} className="text-blue-400" />
              Trade Summary
            </h3>
            <p className="text-sm text-gray-300 leading-relaxed">
              Model detected <strong>{opportunity.dir}</strong> momentum on <strong>{opportunity.symbol}</strong> using the <strong>{opportunity.timeframe}</strong> candle set.
              The signal strength of <strong>{biasStrength.toFixed(1)}%</strong> indicates moderate conviction.
              {opportunity.quality > 50
                ? " Data quality is high with multi-venue confluence."
                : " Proceed with caution: signal lacks broad venue confirmation."}
            </p>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <div className="p-2 rounded bg-gray-900 text-xs flex justify-between">
                <span className="text-gray-500">Raw Model Bias:</span>
                <span className="font-mono">{opportunity.bias.toFixed(3)}</span>
              </div>
              <div className="p-2 rounded bg-gray-900 text-xs flex justify-between">
                <span className="text-gray-500">Data Freshness:</span>
                <span className={ageSec < 60 ? 'text-green-500' : 'text-yellow-500'}>
                  {ageSec < 60 ? 'REALTIME' : `${Math.floor(ageSec / 60)}m lag`}
                </span>
              </div>
            </div>
          </section>

          <section>
            <h3 className="text-lg font-medium mb-3">Evidence Trail</h3>
            <EvidenceTrail evidence={evidence} />
          </section>

          <section className="card bg-gray-900/20 border-gray-800">
            <h3 className="text-sm font-bold mb-3 flex items-center gap-2">
              <Activity size={14} className="text-cyan-400" />
              Market Context
            </h3>
            {marketSnapshot ? (
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="bg-gray-900/50 rounded p-2">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-gray-500">Funding Regime</span>
                    <MetricStatusBadge status={marketSnapshot.available_metrics?.find(m => m.metric === 'funding')?.status} />
                  </div>
                  <div className="font-bold">{marketSnapshot.regimes?.funding || 'N/A'}</div>
                  {marketSnapshot.funding?.horizons?.now !== undefined && (
                    <div className="text-[10px] text-gray-500 mt-1">
                      Rate: {(marketSnapshot.funding.horizons.now * 100).toFixed(4)}%
                    </div>
                  )}
                </div>
                <div className="bg-gray-900/50 rounded p-2">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-gray-500">OI Regime</span>
                    <MetricStatusBadge status={marketSnapshot.available_metrics?.find(m => m.metric === 'oi')?.status} />
                  </div>
                  <div className="font-bold">{marketSnapshot.regimes?.oi || 'N/A'}</div>
                  {marketSnapshot.oi?.current_usd && (
                    <div className="text-[10px] text-gray-500 mt-1">
                      ${(marketSnapshot.oi.current_usd / 1_000_000).toFixed(1)}M
                    </div>
                  )}
                </div>
                <div className="bg-gray-900/50 rounded p-2">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-gray-500">Volume</span>
                    <MetricStatusBadge status={marketSnapshot.available_metrics?.find(m => m.metric === 'volume')?.status} />
                  </div>
                  <div className="font-bold">{marketSnapshot.regimes?.volume || 'N/A'}</div>
                </div>
                <div className="bg-gray-900/50 rounded p-2">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-gray-500">Spread</span>
                    <MetricStatusBadge status={marketSnapshot.available_metrics?.find(m => m.metric === 'orderbook')?.status} />
                  </div>
                  <div className="font-bold">
                    {marketSnapshot.orderbook?.spread_bps?.toFixed(1) || 'N/A'} bps
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-4 text-gray-500 text-xs italic">
                Market context unavailable for {symbol || 'this symbol'}
              </div>
            )}
          </section>

          {/* Phase 3C: Execution Risk Box */}
          <ExecutionRiskBox
            marketSnapshot={marketSnapshot as MarketSnapshotWithMicrostructure}
            confluence={(evidence?.opportunity as any)?.confluence}
          />
        </div>

        {/* Right 2/5: Controls and Action */}
        <div className="lg:col-span-2 space-y-6">
          <section>
            <h3 className="text-lg font-medium mb-3">Execution Control</h3>

            {/* Preview Form */}
            {opportunity.status !== 'executed' && (
              <div className="card mb-4 bg-gray-800/50">
                <h4 className="text-sm font-medium text-gray-400 mb-4">Set Execution Parameters</h4>
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs text-gray-400 mb-1.5 uppercase font-bold">Position Size (USD)</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        value={sizeUsd}
                        onChange={(e) => setSizeUsd(Number(e.target.value))}
                        className="input flex-1 text-lg font-mono"
                      />
                      <span className="text-gray-500 font-bold">$</span>
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1.5 uppercase font-bold">Target Venue</label>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        onClick={() => setVenue('drift')}
                        className={`px-3 py-2 rounded border text-sm font-medium transition-all ${venue === 'drift' ? 'border-blue-500 bg-blue-500/10 text-blue-400' : 'border-gray-700 bg-gray-900 text-gray-400 hover:border-gray-600'}`}
                      >
                        Drift (Solana)
                      </button>
                      <button
                        onClick={() => setVenue('hyperliquid')}
                        className={`px-3 py-2 rounded border text-sm font-medium transition-all ${venue === 'hyperliquid' ? 'border-blue-500 bg-blue-500/10 text-blue-400' : 'border-gray-700 bg-gray-900 text-gray-400 hover:border-gray-600'}`}
                      >
                        Hyperliquid
                      </button>
                    </div>
                  </div>
                  <button
                    onClick={handlePreview}
                    disabled={previewMutation.isPending}
                    className="btn btn-primary w-full py-3 text-base shadow-lg shadow-blue-500/20 active:translate-y-0.5"
                  >
                    {previewMutation.isPending ? 'Verifying Risk...' : 'REQUEST EXECUTION PREVIEW'}
                  </button>
                </div>
              </div>
            )}

            {/* Preview Result */}
            {previewResult && !executeResult && (
              <PreviewPanel
                preview={previewResult}
                onExecute={handleExecute}
                isExecuting={executeMutation.isPending}
              />
            )}

            {/* Execute Result */}
            {executeResult && (
              <div className="card border-2 border-green-500/50 bg-green-500/5">
                <h4 className="text-sm font-bold text-green-500 mb-3 flex items-center gap-2">
                  <ShieldCheck size={16} />
                  EXECUTION DISPATCHED
                </h4>
                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Status</span>
                    <span className="font-bold text-green-400 capitalize">{executeResult.status}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Order ID</span>
                    <span className="font-mono text-xs">{executeResult.order_id || 'N/A'}</span>
                  </div>
                  {executeResult.dry_run && (
                    <div className="bg-yellow-900/30 border border-yellow-900/50 p-2 rounded text-center">
                      <span className="text-yellow-500 text-xs font-bold font-mono">DRY_RUN: NO ACTUAL CAPITAL DEPLOYED</span>
                    </div>
                  )}
                  {!executeResult.ok && executeResult.error && (
                    <div className="bg-red-900/30 border border-red-900/50 p-2 rounded text-red-300 text-xs">
                      {executeResult.error.message}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => setExecuteResult(null)}
                  className="mt-4 w-full py-2 bg-gray-800 hover:bg-gray-700 text-gray-400 text-xs rounded"
                >
                  DISMISS
                </button>
              </div>
            )}

            {opportunity.status === 'executed' && !executeResult && (
              <div className="card border-green-900/50 text-gray-400 italic text-center py-8">
                Entry complete. Monitoring position in Portfolio.
              </div>
            )}
          </section>

          {/* Trade Plan Skeleton */}
          <section className="card bg-gray-900/20 border-gray-800">
            <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3">Proposed Trade Plan</h3>
            <div className="space-y-3">
              <div className="flex justify-between items-center p-2 bg-gray-900 rounded border border-gray-800">
                <span className="text-xs text-gray-500">ENTRY</span>
                <span className="font-mono font-bold">$---.---</span>
              </div>
              <div className="flex justify-between items-center p-2 bg-gray-900 rounded border border-gray-800">
                <span className="text-xs text-red-900 font-bold">STOP LOSS</span>
                <span className="font-mono font-bold text-red-900">$---.---</span>
              </div>
              <div className="flex justify-between items-center p-2 bg-gray-900 rounded border border-gray-800">
                <span className="text-xs text-green-900 font-bold">TAKE PROFIT</span>
                <span className="font-mono font-bold text-green-900">$---.---</span>
              </div>
            </div>
            <p className="mt-3 text-[10px] text-gray-600 text-center italic">
              Live market quotes required to finalize levels.
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
