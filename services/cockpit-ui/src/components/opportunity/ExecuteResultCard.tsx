import type { ExecutionResult } from '../../api/types'
import { ShieldCheck } from 'lucide-react'

export function ExecuteResultCard({ executeResult, onDismiss }: { executeResult: ExecutionResult; onDismiss: () => void }) {
  return (
    <div className="card border-2 border-green-500/50 bg-green-500/5">
      <h4 className="text-sm font-bold text-green-500 mb-3 flex items-center gap-2">
        <ShieldCheck size={16} />
        EXECUTION DISPATCHED
      </h4>
      <div className="space-y-3">
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Status</span>
          <span className="font-bold text-green-400 capitalize">{executeResult.status}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Order ID</span>
          <span className="font-mono text-xs">{executeResult.order_id || 'N/A'}</span>
        </div>
        {executeResult.dry_run && (
          <div className="bg-yellow-900/30 border border-yellow-900/50 p-2 rounded text-center">
            <span className="text-yellow-500 text-xs font-bold font-mono">PAPER ORDER · NOT SENT TO A VENUE</span>
          </div>
        )}
        {!executeResult.ok && executeResult.error && (
          <div className="bg-red-900/30 border border-red-900/50 p-2 rounded text-red-300 text-xs">
            {executeResult.error.message}
          </div>
        )}
      </div>
      <button
        onClick={onDismiss}
        className="mt-4 w-full py-2 bg-gray-800 hover:bg-gray-700 text-gray-400 text-xs rounded"
      >
        DISMISS
      </button>
    </div>
  )
}
