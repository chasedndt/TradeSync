import type { Opportunity } from '../../api/types'
import { Info } from 'lucide-react'

interface TradeSummaryProps {
  opportunity: Opportunity
  biasStrength: number
  ageSec: number
}

export function TradeSummary({ opportunity, biasStrength, ageSec }: TradeSummaryProps) {
  return (
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
  )
}
