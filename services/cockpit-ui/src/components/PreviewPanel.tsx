import { useState } from 'react'
import type { PreviewResponse } from '../api/types'
import { DryRunBanner } from './DryRunBanner'
import { useExecution } from '../context'
import { AlertCircle, CheckCircle2, XCircle, AlertTriangle, Info, Shield, Hash } from 'lucide-react'

interface PreviewPanelProps {
  preview: PreviewResponse
  onExecute: (decisionId: string) => void
  isExecuting: boolean
}

// Map reason codes to user-friendly messages
const reasonCodeExplanations: Record<string, { title: string; fix?: string }> = {
  EXPIRED: {
    title: 'Opportunity Expired',
    fix: 'The opportunity window has closed. Wait for a new signal.'
  },
  SIZE_TOO_SMALL: {
    title: 'Position Size Too Small',
    fix: 'Increase the position size to meet the minimum requirement.'
  },
  SIZE_TOO_LARGE: {
    title: 'Position Size Too Large',
    fix: 'Reduce the position size to stay within risk limits.'
  },
  QUALITY_TOO_LOW: {
    title: 'Signal Quality Below Threshold',
    fix: 'Wait for a higher quality signal or adjust min_quality policy.'
  },
  BLACKLISTED: {
    title: 'Symbol Blacklisted',
    fix: 'This symbol is on the blacklist. Remove it from risk policies to trade.'
  },
  COOLDOWN_ACTIVE: {
    title: 'Cooldown Period Active',
    fix: 'Recent activity on this symbol. Wait for cooldown to expire.'
  },
  DAILY_LIMIT_REACHED: {
    title: 'Daily Notional Limit Reached',
    fix: 'You have reached your daily trading limit. Resume tomorrow.'
  },
  SIGNAL_STALE: {
    title: 'Signal Data Stale',
    fix: 'The underlying signal is too old. Wait for fresh data.'
  }
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

      {/* Execute Button */}
      {risk_verdict.allowed && decision_id && (
        <div className="pt-4 border-t border-gray-800">
          {/* Mode Warning */}
          {mode === 'observe' && (
            <div className="bg-blue-900/20 border border-blue-900/50 p-3 rounded mb-4 text-sm text-blue-300 flex items-center gap-2">
              <AlertCircle size={16} />
              You are in Observe mode. Switch to Manual mode in Execution settings to enable trading.
            </div>
          )}

          {/* Confirmation Checkbox */}
          <label className="flex items-start gap-3 p-3 bg-blue-900/10 rounded-lg border border-blue-900/30 cursor-pointer mb-4">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              className="mt-0.5 rounded bg-gray-900 border-gray-700 text-blue-600 focus:ring-blue-500"
            />
            <div className="text-xs text-blue-300 leading-relaxed font-medium">
              {isDryRun ? (
                <>I understand this is a <strong>DRY RUN</strong> simulation. No real capital will be deployed.</>
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
            {isExecuting ? 'DISPATCHING TO VENUE...' : isDryRun ? 'SIMULATE EXECUTION' : 'CONFIRM & EXECUTE'}
          </button>
        </div>
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
