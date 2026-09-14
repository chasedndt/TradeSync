import type { MarketSnapshot, MetricStatus } from '../../api/types'
import { Activity } from 'lucide-react'

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

export function MarketContextCard({ marketSnapshot, symbol }: { marketSnapshot?: MarketSnapshot; symbol: string }) {
  return (
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
  )
}
