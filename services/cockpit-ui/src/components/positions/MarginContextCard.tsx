import { Shield, Percent } from 'lucide-react'
import type { Position } from '../../api/types'

interface MarginContextCardProps {
  positions?: Position[]
  weightedLeverage: number
  maxLeverage: number
  maxPositions: number
  totalPnl: number
  totalExposure: number
  dailyUsagePercent: number
}

export function MarginContextCard({ positions, weightedLeverage, maxLeverage, maxPositions, totalPnl, totalExposure, dailyUsagePercent }: MarginContextCardProps) {
  return (
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
  )
}
