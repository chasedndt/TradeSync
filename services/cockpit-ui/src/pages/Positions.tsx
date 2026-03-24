import { useState } from 'react'
import { usePositions, useRiskLimits } from '../api/hooks'
import { DirectionBadge, DryRunBanner } from '../components'
import { useExecution } from '../context/ExecutionContext'
import { AlertTriangle, TrendingUp, Shield, DollarSign, Percent, Activity } from 'lucide-react'

const venueOptions = ['all', 'drift', 'hyperliquid']

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
        <div className="card">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="w-4 h-4 text-blue-400" />
            <h3 className="font-semibold text-gray-200">Exposure Summary</h3>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-gray-400 flex items-center gap-1">
                <DollarSign className="w-3 h-3" /> Total Notional
              </div>
              <div className="text-xl font-bold text-blue-400">
                ${totalExposure.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>
            <div>
              <div className="text-gray-400 flex items-center gap-1">
                <Activity className="w-3 h-3" /> Positions
              </div>
              <div className="text-xl font-bold">
                {positions?.length || 0} / {maxPositions || '∞'}
              </div>
            </div>
          </div>
          {/* Daily Usage Bar */}
          {dailyLimit > 0 && (
            <div className="mt-4">
              <div className="flex justify-between text-xs text-gray-400 mb-1">
                <span>Daily Usage</span>
                <span>${dailyUsage.toLocaleString()} / ${dailyLimit.toLocaleString()}</span>
              </div>
              <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    dailyUsagePercent > 90 ? 'bg-red-500' : dailyUsagePercent > 70 ? 'bg-yellow-500' : 'bg-green-500'
                  }`}
                  style={{ width: `${Math.min(dailyUsagePercent, 100)}%` }}
                />
              </div>
              <div className="text-xs text-gray-500 mt-1">{dailyUsagePercent.toFixed(1)}% utilized</div>
            </div>
          )}
        </div>

        {/* Margin Context Card */}
        <div className="card">
          <div className="flex items-center gap-2 mb-3">
            <Shield className="w-4 h-4 text-purple-400" />
            <h3 className="font-semibold text-gray-200">Margin Context</h3>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-gray-400 flex items-center gap-1">
                <Percent className="w-3 h-3" /> Avg Leverage
              </div>
              <div className={`text-xl font-bold ${weightedLeverage > maxLeverage * 0.8 ? 'text-yellow-400' : 'text-green-400'}`}>
                {weightedLeverage.toFixed(1)}x
              </div>
              <div className="text-xs text-gray-500">max {maxLeverage}x allowed</div>
            </div>
            <div>
              <div className="text-gray-400">Total PnL</div>
              <div className={`text-xl font-bold ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${totalPnl.toFixed(2)}
              </div>
              <div className="text-xs text-gray-500">
                {totalExposure > 0 ? `${((totalPnl / totalExposure) * 100).toFixed(2)}% ROI` : '--'}
              </div>
            </div>
          </div>
          {/* Risk Indicator */}
          <div className="mt-4 p-2 rounded bg-gray-800/50 text-xs text-gray-400">
            <span className="font-medium text-gray-300">Risk Status:</span>{' '}
            {positions && positions.length >= maxPositions ? (
              <span className="text-red-400">Position limit reached</span>
            ) : dailyUsagePercent > 90 ? (
              <span className="text-red-400">Near daily limit</span>
            ) : weightedLeverage > maxLeverage * 0.8 ? (
              <span className="text-yellow-400">High leverage exposure</span>
            ) : (
              <span className="text-green-400">Within risk parameters</span>
            )}
          </div>
        </div>
      </div>

      {positions && positions.length === 0 && (
        <div className="text-gray-500 text-center py-8">No open positions</div>
      )}

      {positions && positions.length > 0 && (
        <>

          {/* Positions Table */}
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 border-b border-gray-700">
                  <th className="pb-2">Symbol</th>
                  <th className="pb-2">Venue</th>
                  <th className="pb-2">Side</th>
                  <th className="pb-2">Size</th>
                  <th className="pb-2">Entry</th>
                  <th className="pb-2">Mark</th>
                  <th className="pb-2">PnL</th>
                  <th className="pb-2">Leverage</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, idx) => (
                  <tr key={idx} className="border-b border-gray-800">
                    <td className="py-2 font-medium">{pos.symbol}</td>
                    <td className="py-2 text-gray-400 capitalize">{pos.venue}</td>
                    <td className="py-2">
                      <DirectionBadge direction={pos.side} />
                    </td>
                    <td className="py-2">${pos.size_usd.toFixed(2)}</td>
                    <td className="py-2">${pos.entry_price.toFixed(4)}</td>
                    <td className="py-2">${pos.mark_price.toFixed(4)}</td>
                    <td className={`py-2 ${pos.pnl_usd >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${pos.pnl_usd.toFixed(2)}
                    </td>
                    <td className="py-2">{pos.leverage}x</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
