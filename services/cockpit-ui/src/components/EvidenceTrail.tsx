import type { EvidenceResponse } from '../api/types'
import { StatusBadge } from './StatusBadge'
import { DirectionBadge } from './DirectionBadge'
import { Activity, Zap, Shield, FileText } from 'lucide-react'

interface EvidenceTrailProps {
  evidence: EvidenceResponse
}

export function EvidenceTrail({ evidence }: EvidenceTrailProps) {
  const { signals, events, decisions, exec_orders } = evidence

  return (
    <div className="space-y-6">
      {/* Signals */}
      <section>
        <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3 flex items-center gap-2">
          <Zap size={14} />
          Logic Signals
        </h3>
        <div className="space-y-3">
          {signals.map((signal) => (
            <div key={signal.id} className="card bg-gray-900/40 border-gray-800 p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="font-bold text-sm text-blue-400">{signal.agent.toUpperCase()}</span>
                <DirectionBadge direction={signal.dir} />
              </div>
              <div className="grid grid-cols-2 gap-4 text-xs mb-3">
                <div>
                  <span className="text-gray-500">Kind:</span> <span className="text-gray-300">{signal.kind}</span>
                </div>
                <div>
                  <span className="text-gray-500">Confidence:</span> <span className="text-gray-300 font-mono">{(signal.confidence * 100).toFixed(1)}%</span>
                </div>
              </div>
              {signal.features && (
                <div className="text-[10px] text-gray-500 bg-black/40 p-2 rounded font-mono">
                  {Object.entries(signal.features).map(([k, v]) => (
                    <div key={k} className="flex justify-between">
                      <span>{k}:</span>
                      <span className="text-blue-300">{String(v)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
          {signals.length === 0 && <div className="text-xs text-gray-600 italic">No logic signals recorded for this window.</div>}
        </div>
      </section>

      {/* Events */}
      <section>
        <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3 flex items-center gap-2">
          <Activity size={14} />
          Raw Market Events
        </h3>
        <div className="space-y-2 max-h-96 overflow-y-auto pr-2 custom-scrollbar">
          {events.map((event) => (
            <div key={event.id} className="bg-gray-900/30 border border-gray-800/50 rounded p-2 text-[10px] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-gray-500 font-mono">{new Date(event.ts).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                <span className="font-bold text-gray-400 w-16">{event.source.toUpperCase()}</span>
                <span className="text-blue-500/80">{event.kind}</span>
                {'mark' in event.payload && event.payload.mark != null && (
                  <span className="text-gray-300 font-mono">${Number(event.payload.mark as string).toLocaleString()}</span>
                )}
                {'funding' in event.payload && event.payload.funding != null && (
                  <span className={Number(event.payload.funding as string) > 0 ? 'text-red-400' : 'text-green-400'}>
                    {Number(event.payload.funding as string).toFixed(5)}
                  </span>
                )}
              </div>
              <details className="relative">
                <summary className="cursor-pointer text-gray-700 hover:text-gray-500 list-none">
                  <FileText size={12} />
                </summary>
                <pre className="absolute right-0 top-full mt-1 w-64 bg-black border border-gray-800 p-2 z-10 rounded shadow-2xl overflow-auto max-h-48 text-[10px]">
                  {JSON.stringify(event.payload, null, 2)}
                </pre>
              </details>
            </div>
          ))}
        </div>
      </section>

      {/* Decisions & Orders */}
      {(decisions.length > 0 || exec_orders.length > 0) && (
        <section>
          <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3 flex items-center gap-2">
            <Shield size={14} />
            Execution Audit
          </h3>
          <div className="space-y-3">
            {decisions.map((decision) => (
              <div key={decision.id} className="card bg-gray-900/40 border-gray-800 p-3">
                <div className="flex items-center justify-between text-xs mb-2">
                  <span className="font-bold text-gray-400 uppercase">Risk Decision</span>
                  <span className="text-gray-600 font-mono">{decision.id.slice(0, 8)}</span>
                </div>
                <div className="text-[10px] text-gray-400">
                  Venue: <span className="text-gray-200 capitalize">{decision.venue}</span>
                </div>
              </div>
            ))}
            {exec_orders.map((order) => (
              <div key={order.id} className="card bg-blue-900/5 border-blue-500/20 p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-bold text-sm text-blue-400">Order Dispatch</span>
                  <StatusBadge status={order.status} />
                </div>
                <div className="text-[10px] text-gray-500 flex justify-between">
                  <span>{order.venue.toUpperCase()}</span>
                  <span>{order.dry_run ? 'DRY_RUN' : 'LIVE'}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
