import { useState } from 'react'
import type { PreviewResponse } from '../api/types'
import { DryRunBanner } from './DryRunBanner'
import { useExecution } from '../context'
import { Shield, Hash } from 'lucide-react'
import { ExecuteConfirm } from './preview/ExecuteConfirm'
import { PlanDetails } from './preview/PlanDetails'
import { reasonCodeExplanations } from './preview/reasonCodes'
import { RiskVerdictBox } from './preview/RiskVerdictBox'

interface PreviewPanelProps {
  preview: PreviewResponse
  onExecute: (decisionId: string) => void
  isExecuting: boolean
}

export function PreviewPanel({ preview, onExecute, isExecuting }: PreviewPanelProps) {
  const [confirmed, setConfirmed] = useState(false)
  const { canExecute, mode, isDryRun } = useExecution()
  const { decision_id, plan, risk_verdict, suggested_adjustments } = preview

  // Extract reason_code if available (from updated API)
  const reasonCode = (risk_verdict as Record<string, unknown>).reason_code as string | undefined
  const reasonExplanation = reasonCode ? reasonCodeExplanations[reasonCode] : undefined

  const handleExecute = () => {
    if (decision_id && confirmed && canExecute) {
      onExecute(decision_id)
    }
  }

  const executeDisabled = !confirmed || isExecuting || !canExecute

  return (
    <div className="card space-y-4 border-2 border-blue-500/30">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="font-bold flex items-center gap-2">
          <Shield size={18} className="text-blue-500" />
          Execution Preview
        </h3>
        <div className="flex items-center gap-2">
          {decision_id && (
            <span className="text-[10px] font-mono text-gray-500 flex items-center gap-1" title="Decision ID">
              <Hash size={10} />
              {decision_id.slice(0, 8)}
            </span>
          )}
        </div>
      </div>

      {/* Dry Run Banner */}
      <DryRunBanner variant="compact" />

      {/* Risk Verdict - Enhanced */}
      <RiskVerdictBox riskVerdict={risk_verdict} reasonCode={reasonCode} reasonExplanation={reasonExplanation} />

      <PlanDetails plan={plan} riskVerdict={risk_verdict} suggestedAdjustments={suggested_adjustments} />

      {/* Execute Button */}
      {risk_verdict.allowed && decision_id && (
        <ExecuteConfirm
          mode={mode}
          isDryRun={isDryRun}
          confirmed={confirmed}
          onConfirmedChange={setConfirmed}
          onExecute={handleExecute}
          executeDisabled={executeDisabled}
          isExecuting={isExecuting}
        />
      )}

      {!risk_verdict.allowed && (
        <div className="bg-red-900/10 border border-red-900/30 p-4 rounded-lg text-center">
          <p className="text-sm font-bold text-red-500 mb-1 tracking-tight">EXECUTION HALTED</p>
          <p className="text-[10px] text-red-400">
            {reasonExplanation?.fix || 'This intent violates one or more active risk policies and cannot be dispatched.'}
          </p>
        </div>
      )}
    </div>
  )
}
