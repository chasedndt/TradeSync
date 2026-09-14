import type { Opportunity } from '../../api/types'
import { StatusBadge } from '../StatusBadge'
import { DirectionBadge } from '../DirectionBadge'
import { ShieldCheck, TrendingUp } from 'lucide-react'

interface OpportunityHeaderProps {
  opportunity: Opportunity
  biasStrength: number
  ageSec: number
}

export function OpportunityHeader({ opportunity, biasStrength, ageSec }: OpportunityHeaderProps) {
  return (
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
  )
}
