import { useState } from 'react'
import { usePositions, useRiskLimits } from '../api/hooks'
import { DryRunBanner } from '../components'
import { useExecution } from '../context/ExecutionContext'
import { AlertTriangle } from 'lucide-react'
import { ExposureSummaryCard } from '../components/positions/ExposureSummaryCard'
import { MarginContextCard } from '../components/positions/MarginContextCard'
import { PositionsTable } from '../components/positions/PositionsTable'

const venueOptions = ['all', 'hyperliquid']

export function Positions() {
  const [venue, setVenue] = useState('all')
  const { data: positions, isLoading, error } = usePositions(venue)
  const { data: riskLimits } = useRiskLimits()
  const { isDryRun, isDemo } = useExecution()

  const totalPnl = positions?.reduce((sum, p) => sum + p.pnl_usd, 0) || 0
  const totalExposure = positions?.reduce((sum, p) => sum + p.size_usd, 0) || 0
  const weightedLeverage = positions && positions.length > 0
    ? positions.reduce((sum, p) => sum + (p.leverage * p.size_usd), 0) / totalExposure
    : 0

  // Daily notional usage from risk limits
  const dailyLimit = riskLimits?.daily_notional_limit || 0
  const dailyUsage = riskLimits?.current_counters?.daily_notional_usage || 0
  const dailyUsagePercent = dailyLimit > 0 ? (dailyUsage / dailyLimit) * 100 : 0
  const maxLeverage = riskLimits?.max_leverage || 0
  const maxPositions = riskLimits?.max_open_positions || 0

  // Data truth indicator
  const dataMode = isDemo ? 'DEMO' : isDryRun ? 'PAPER' : 'LIVE'
  const dataModeColor = isDemo ? 'bg-gray-600' : isDryRun ? 'bg-yellow-600' : 'bg-green-600'

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-bold">Open Positions</h2>
          <span className={`px-2 py-0.5 text-xs font-bold rounded ${dataModeColor}`}>
            {dataMode} DATA
          </span>
        </div>
        <div className="flex gap-2">
          {venueOptions.map((v) => (
            <button
              key={v}
              onClick={() => setVenue(v)}
              className={`px-3 py-1 rounded text-sm capitalize ${venue === v
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      <DryRunBanner variant="compact" />

      {/* Data Truth Warning */}
      {isDemo && (
        <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-3 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-gray-400" />
          <div className="text-sm text-gray-400">
            <span className="font-medium text-gray-300">Demo Mode:</span> Positions shown are simulated. No real capital is at risk.
          </div>
        </div>
      )}

      {isLoading && <div className="text-gray-400">Loading...</div>}
      {error && <div className="text-red-400">Error loading positions</div>}

      {/* Exposure Summary & Margin Context - Always show */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Exposure Summary Card */}
        <ExposureSummaryCard
          positions={positions}
          totalExposure={totalExposure}
          maxPositions={maxPositions}
          dailyLimit={dailyLimit}
          dailyUsage={dailyUsage}
          dailyUsagePercent={dailyUsagePercent}
        />

        {/* Margin Context Card */}
        <MarginContextCard
          positions={positions}
          weightedLeverage={weightedLeverage}
          maxLeverage={maxLeverage}
          maxPositions={maxPositions}
          totalPnl={totalPnl}
          totalExposure={totalExposure}
          dailyUsagePercent={dailyUsagePercent}
        />
      </div>

      {positions && positions.length === 0 && (
        <div className="text-gray-500 text-center py-8">No open positions</div>
      )}

      {positions && positions.length > 0 && (
        <>

          {/* Positions Table */}
          <PositionsTable positions={positions} />
        </>
      )}
    </div>
  )
}
