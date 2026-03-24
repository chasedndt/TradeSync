import { Link } from 'react-router-dom'
import type { Opportunity } from '../api/types'
import { StatusBadge } from './StatusBadge'
import { DirectionBadge } from './DirectionBadge'
import { calculateBiasStrength } from '../utils/metrics'
import { Clock, AlertTriangle } from 'lucide-react'

const OPPORTUNITY_TTL_SECONDS = 300 // 5 minutes

interface OpportunityCardProps {
  opportunity: Opportunity
}

export function OpportunityCard({ opportunity }: OpportunityCardProps) {
  const { id, symbol, timeframe, bias, quality, dir, status, snapshot_ts } = opportunity

  const biasStrength = calculateBiasStrength(bias)
  const ageMs = Date.now() - new Date(snapshot_ts).getTime()
  const ageSec = Math.floor(ageMs / 1000)
  const ageMin = Math.floor(ageSec / 60)

  // Derive display status from timestamps
  const isExpired = ageSec > OPPORTUNITY_TTL_SECONDS
  const displayStatus = isExpired ? 'expired' : status

  // Freshness indicator
  const isFresh = ageSec < 60
  const isStale = ageSec > 180 // 3+ minutes

  return (
    <Link
      to={`/opportunities/${id}`}
      className={`card block hover:border-gray-600 transition-colors ${isExpired ? 'opacity-60' : ''}`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-bold">{symbol}</span>
          <span className="text-xs bg-gray-800 px-1.5 py-0.5 rounded text-gray-400">{timeframe}</span>
        </div>
        <StatusBadge status={displayStatus} />
      </div>

      <div className="grid grid-cols-3 gap-4 text-sm">
        <div>
          <div className="text-gray-500 text-xs">Direction</div>
          <DirectionBadge direction={dir} />
        </div>
        <div title={`Raw model score: ${bias.toFixed(3)}`}>
          <div className="text-gray-500 text-xs">Strength</div>
          <div className="font-medium">{biasStrength.toFixed(0)}%</div>
          <div className="h-1 bg-gray-800 rounded-full overflow-hidden mt-1">
            <div
              className="h-full bg-blue-500 transition-all"
              style={{ width: `${Math.min(biasStrength, 100)}%` }}
            />
          </div>
        </div>
        <div title="Model confidence score">
          <div className="text-gray-500 text-xs">Quality</div>
          <div className="font-medium">{quality.toFixed(0)}%</div>
          <div className="h-1 bg-gray-800 rounded-full overflow-hidden mt-1">
            <div
              className={`h-full transition-all ${quality >= 50 ? 'bg-green-500' : 'bg-yellow-500'}`}
              style={{ width: `${Math.min(quality, 100)}%` }}
            />
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between text-xs">
        <span className="text-gray-500">{new Date(snapshot_ts).toLocaleTimeString()}</span>
        <span className={`flex items-center gap-1 ${isFresh ? 'text-green-500' : isStale ? 'text-yellow-500' : 'text-gray-500'}`}>
          {isStale && <AlertTriangle size={10} />}
          {!isStale && <Clock size={10} />}
          {ageMin > 0 ? `${ageMin}m ago` : 'just now'}
        </span>
      </div>
    </Link>
  )
}
