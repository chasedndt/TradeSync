import { TrendingUp, DollarSign, Activity } from 'lucide-react'
import type { Position } from '../../api/types'

interface ExposureSummaryCardProps {
  positions?: Position[]
  totalExposure: number
  maxPositions: number
  dailyLimit: number
  dailyUsage: number
  dailyUsagePercent: number
}

export function ExposureSummaryCard({ positions, totalExposure, maxPositions, dailyLimit, dailyUsage, dailyUsagePercent }: ExposureSummaryCardProps) {
  return (
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
  )
}
