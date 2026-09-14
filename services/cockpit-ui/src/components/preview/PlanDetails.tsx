import type { PreviewResponse } from '../../api/types'
import { CheckCircle2, XCircle, AlertTriangle } from 'lucide-react'

interface PlanDetailsProps {
  plan: PreviewResponse['plan']
  riskVerdict: PreviewResponse['risk_verdict']
  suggestedAdjustments: PreviewResponse['suggested_adjustments']
}

export function PlanDetails({ plan, riskVerdict: risk_verdict, suggestedAdjustments: suggested_adjustments }: PlanDetailsProps) {
  return (
    <>
      {/* Plan Details */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-gray-900/50 p-3 rounded border border-gray-800">
          <div className="text-[10px] text-gray-500 uppercase mb-1">Action</div>
          <div className="text-sm font-bold">{String(plan.action)}</div>
        </div>
        <div className="bg-gray-900/50 p-3 rounded border border-gray-800">
          <div className="text-[10px] text-gray-500 uppercase mb-1">Asset</div>
          <div className="text-sm font-bold">{String(plan.symbol)}</div>
        </div>
        <div className="bg-gray-900/50 p-3 rounded border border-gray-800">
          <div className="text-[10px] text-gray-500 uppercase mb-1">Size</div>
          <div className="text-sm font-bold text-blue-400">${Number(plan.size_usd).toLocaleString()}</div>
        </div>
        <div className="bg-gray-900/50 p-3 rounded border border-gray-800">
          <div className="text-[10px] text-gray-500 uppercase mb-1">Venue</div>
          <div className="text-sm font-bold capitalize">{String(plan.venue)}</div>
        </div>
      </div>

      {/* Trade Plan (if available) */}
      {(plan.entry != null || plan.stop_loss != null || plan.take_profit != null) && (
        <div className="space-y-2">
          <div className="text-xs font-bold text-gray-500 uppercase">Trade Plan</div>
          <div className="grid grid-cols-3 gap-2">
            {plan.entry != null && (
              <div className="bg-gray-900 p-2 rounded text-center">
                <div className="text-[10px] text-gray-500">ENTRY</div>
                <div className="font-mono font-bold">${Number(plan.entry).toLocaleString()}</div>
              </div>
            )}
            {plan.stop_loss != null && (
              <div className="bg-gray-900 p-2 rounded text-center">
                <div className="text-[10px] text-red-500">STOP LOSS</div>
                <div className="font-mono font-bold text-red-400">${Number(plan.stop_loss).toLocaleString()}</div>
              </div>
            )}
            {plan.take_profit != null && (
              <div className="bg-gray-900 p-2 rounded text-center">
                <div className="text-[10px] text-green-500">TAKE PROFIT</div>
                <div className="font-mono font-bold text-green-400">${Number(plan.take_profit).toLocaleString()}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Risk Checks */}
      {risk_verdict.checks && Object.keys(risk_verdict.checks).length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs font-bold text-gray-500 uppercase mb-1">Policy Checks</div>
          {Object.entries(risk_verdict.checks).map(([check, passed]) => (
            <div key={check} className="flex items-center justify-between text-xs p-2 bg-gray-900/30 rounded">
              <span className="text-gray-400">{check.replace(/_/g, ' ')}</span>
              <div className="flex items-center gap-1">
                {passed ? (
                  <CheckCircle2 size={12} className="text-green-500" />
                ) : (
                  <XCircle size={12} className="text-red-500" />
                )}
                <span className={passed ? 'text-green-500' : 'text-red-500 font-bold'}>
                  {passed ? 'PASS' : 'FAIL'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Suggested Adjustments */}
      {suggested_adjustments && Object.keys(suggested_adjustments).length > 0 && (
        <div className="bg-yellow-900/10 border border-yellow-900/30 p-3 rounded-lg">
          <div className="text-xs font-bold text-yellow-600 uppercase mb-2 flex items-center gap-1">
            <AlertTriangle size={12} />
            Suggested Adjustments
          </div>
          <pre className="text-[10px] text-yellow-500 font-mono overflow-auto">
            {JSON.stringify(suggested_adjustments, null, 2)}
          </pre>
        </div>
      )}
    </>
  )
}
