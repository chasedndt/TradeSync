import type { MarketSnapshotWithMicrostructure, Confluence } from '../../api/types'
import { AlertTriangle, Shield, AlertCircle } from 'lucide-react'

// Phase 3C: Execution Risk Box Component
export function ExecutionRiskBox({
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
