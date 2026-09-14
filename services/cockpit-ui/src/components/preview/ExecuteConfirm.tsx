import type { ExecutionMode } from '../../context'
import { AlertCircle } from 'lucide-react'

interface ExecuteConfirmProps {
  mode: ExecutionMode
  paperOnly: boolean
  confirmed: boolean
  onConfirmedChange: (confirmed: boolean) => void
  onExecute: () => void
  executeDisabled: boolean
  isExecuting: boolean
}

export function ExecuteConfirm({ mode, paperOnly, confirmed, onConfirmedChange, onExecute: handleExecute, executeDisabled, isExecuting }: ExecuteConfirmProps) {
  return (
    <div className="pt-4 border-t border-gray-800">
      {/* Mode Warning */}
      {mode === 'read_only' && (
        <div className="bg-blue-900/20 border border-blue-900/50 p-3 rounded mb-4 text-sm text-blue-300 flex items-center gap-2">
          <AlertCircle size={16} />
          Read-only mode is on. Switch to Manual mode in Execution settings to submit orders.
        </div>
      )}

      {/* Confirmation Checkbox */}
      <label className="flex items-start gap-3 p-3 bg-blue-900/10 rounded-lg border border-blue-900/30 cursor-pointer mb-4">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => onConfirmedChange(e.target.checked)}
          className="mt-0.5 rounded bg-gray-900 border-gray-700 text-blue-600 focus:ring-blue-500"
        />
        <div className="text-xs text-blue-300 leading-relaxed font-medium">
          {paperOnly ? (
            <>I understand execution is <strong>not connected</strong>: this order is recorded to the paper ledger and no capital is deployed.</>
          ) : (
            <>I verify that this trade plan aligns with my current strategy and I authorize deployment of capital to the blockchain.</>
          )}
        </div>
      </label>

      <button
        onClick={handleExecute}
        disabled={executeDisabled}
        className={`w-full py-3 font-bold rounded-lg transition-all ${
          executeDisabled
            ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
            : 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-500/20 active:translate-y-0.5'
        }`}
      >
        {isExecuting
          ? (paperOnly ? 'RECORDING PAPER ORDER...' : 'DISPATCHING TO VENUE...')
          : paperOnly ? 'RECORD PAPER ORDER' : 'CONFIRM & EXECUTE'}
      </button>
    </div>
  )
}
