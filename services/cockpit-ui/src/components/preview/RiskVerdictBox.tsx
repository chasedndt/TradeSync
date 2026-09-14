import type { PreviewResponse } from '../../api/types'
import { CheckCircle2, XCircle, Info } from 'lucide-react'

interface RiskVerdictBoxProps {
  riskVerdict: PreviewResponse['risk_verdict']
  reasonCode?: string
  reasonExplanation?: { title: string; fix?: string }
}

export function RiskVerdictBox({ riskVerdict: risk_verdict, reasonCode, reasonExplanation }: RiskVerdictBoxProps) {
  return (
    <div className={`p-4 rounded-lg border ${
      risk_verdict.allowed
        ? 'bg-green-900/10 border-green-900/50'
        : 'bg-red-900/10 border-red-900/50'
    }`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          {risk_verdict.allowed ? (
            <CheckCircle2 size={20} className="text-green-500" />
          ) : (
            <XCircle size={20} className="text-red-500" />
          )}
          <span className={`font-bold ${risk_verdict.allowed ? 'text-green-400' : 'text-red-400'}`}>
            {risk_verdict.allowed ? 'EXECUTION ALLOWED' : 'EXECUTION BLOCKED'}
          </span>
        </div>
        {reasonCode && (
          <span className="text-[10px] font-mono bg-gray-800 px-2 py-1 rounded text-gray-400">
            {reasonCode}
          </span>
        )}
      </div>

      {/* Reason */}
      <div className="text-sm text-gray-300 mb-2">
        {reasonExplanation?.title || risk_verdict.reason}
      </div>

      {/* Fix suggestion */}
      {!risk_verdict.allowed && reasonExplanation?.fix && (
        <div className="flex items-start gap-2 text-xs text-yellow-400/80 bg-yellow-900/10 p-2 rounded mt-2">
          <Info size={12} className="mt-0.5 flex-shrink-0" />
          <span>{reasonExplanation.fix}</span>
        </div>
      )}
    </div>
  )
}
