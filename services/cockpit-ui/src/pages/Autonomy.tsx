import { Eye, MousePointer2, Zap, Shield, Lock, AlertTriangle, CheckCircle, XCircle, ArrowRight } from 'lucide-react'
import { useExecution } from '../context'
import { useExecutionStatus } from '../api/hooks'

/**
 * Autonomy page: governance / authority readiness.
 *
 * Responsibility: show WHAT authority the system currently holds and WHAT is
 * required to advance to the next mode.  Mode switching lives on the Execution
 * page — this page explains the why, not the how.
 */
export function Autonomy() {
  const { mode, isDryRun, isDemo } = useExecution()
  const { data: status } = useExecutionStatus()

  const allVenuesConnected = status?.venues?.length > 0 &&
    status.venues.every(v => v.circuit_open !== 'unknown')
  const executionEnabled = status?.execution_enabled === 'true'
  const anyCircuitOpen = status?.venues?.some(v => v.circuit_open === true)

  // Readiness checklist items per mode gate
  const manualReadiness = [
    {
      label: 'All venue exec services reachable',
      met: allVenuesConnected,
      note: 'exec-drift-svc and exec-hl-svc must respond to /circuit-status'
    },
    {
      label: 'Backend execution gate open',
      met: executionEnabled,
      note: 'Set EXECUTION_ENABLED=true in environment, DRY_RUN=false'
    },
    {
      label: 'No circuit breakers tripped',
      met: !anyCircuitOpen,
      note: 'Circuit breakers reset automatically after cooldown'
    },
  ]

  const autonomousReadiness = [
    ...manualReadiness,
    {
      label: 'Wallet/signing authority configured',
      met: false,
      note: 'Phase 3E — server-side key custody or hardware wallet integration'
    },
    {
      label: 'Risk policies reviewed and locked',
      met: false,
      note: 'All limits must be explicitly confirmed before autonomous mode'
    },
    {
      label: 'Audit trail verified active',
      met: false,
      note: 'Full decision/order logging must be confirmed running'
    },
  ]

  const modeLabel = mode === 'observe' ? 'OBSERVE' : mode === 'manual' ? 'MANUAL' : 'AUTONOMOUS'
  const modeBadgeColor = mode === 'observe'
    ? 'bg-blue-900/50 text-blue-400 border-blue-700'
    : mode === 'manual'
      ? 'bg-orange-900/50 text-orange-400 border-orange-700'
      : 'bg-red-900/50 text-red-400 border-red-700'

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Autonomy & Governance</h2>
        <span className={`text-xs px-2 py-1 rounded border font-medium ${modeBadgeColor}`}>
          {modeLabel} MODE
        </span>
      </div>

      <p className="text-sm text-gray-400">
        This page shows current system authority and what prerequisites must be met
        to advance to each mode. To change the active mode, go to{' '}
        <a href="/execution" className="text-blue-400 hover:underline">Execution Control</a>.
      </p>

      {/* Mode progression — read-only, not interactive */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-400 mb-4">Mode Progression</h3>
        <div className="flex items-center gap-2">

          {/* Observe */}
          <div className={`flex-1 rounded-lg p-3 border-2 text-center ${
            mode === 'observe' ? 'border-blue-500 bg-blue-900/10' : 'border-gray-700 opacity-60'
          }`}>
            <Eye size={20} className={`mx-auto mb-1 ${mode === 'observe' ? 'text-blue-400' : 'text-gray-600'}`} />
            <div className={`text-xs font-bold ${mode === 'observe' ? 'text-blue-400' : 'text-gray-500'}`}>
              Observe
            </div>
            {mode === 'observe' && (
              <div className="text-[9px] text-blue-500 mt-0.5">CURRENT</div>
            )}
          </div>

          <ArrowRight size={14} className="text-gray-600 flex-shrink-0" />

          {/* Manual */}
          <div className={`flex-1 rounded-lg p-3 border-2 text-center ${
            mode === 'manual' ? 'border-orange-500 bg-orange-900/10' : 'border-gray-700 opacity-60'
          }`}>
            <MousePointer2 size={20} className={`mx-auto mb-1 ${mode === 'manual' ? 'text-orange-400' : 'text-gray-600'}`} />
            <div className={`text-xs font-bold ${mode === 'manual' ? 'text-orange-400' : 'text-gray-500'}`}>
              Manual
            </div>
            {mode === 'manual' && (
              <div className="text-[9px] text-orange-500 mt-0.5">CURRENT</div>
            )}
          </div>

          <ArrowRight size={14} className="text-gray-600 flex-shrink-0" />

          {/* Autonomous — always locked */}
          <div className="flex-1 rounded-lg p-3 border-2 border-gray-700 opacity-40 text-center relative">
            <Zap size={20} className="mx-auto mb-1 text-gray-600" />
            <div className="text-xs font-bold text-gray-500">Autonomous</div>
            <Lock size={10} className="absolute top-1 right-1 text-gray-600" />
          </div>
        </div>
      </div>

      {/* Readiness Checklists */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* To enable Manual mode */}
        <div className="card">
          <div className="flex items-center gap-2 mb-3">
            <MousePointer2 size={14} className="text-orange-400" />
            <h4 className="font-medium text-sm">Manual Mode Requirements</h4>
            {mode === 'manual' && (
              <span className="text-[9px] bg-orange-900/30 text-orange-400 px-1.5 py-0.5 rounded">ACTIVE</span>
            )}
          </div>
          <div className="space-y-2">
            {manualReadiness.map((item, i) => (
              <div key={i} className="flex items-start gap-2">
                {item.met ? (
                  <CheckCircle size={13} className="text-green-500 mt-0.5 flex-shrink-0" />
                ) : (
                  <XCircle size={13} className="text-red-400 mt-0.5 flex-shrink-0" />
                )}
                <div>
                  <div className="text-xs text-gray-300">{item.label}</div>
                  {!item.met && (
                    <div className="text-[10px] text-gray-600">{item.note}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
          {manualReadiness.every(r => r.met) ? (
            <div className="mt-3 text-xs text-green-400 bg-green-900/20 rounded p-2 flex items-center gap-2">
              <CheckCircle size={12} />
              Infrastructure ready. Switch mode on the Execution page.
            </div>
          ) : (
            <div className="mt-3 text-xs text-yellow-600 bg-yellow-900/20 rounded p-2 flex items-center gap-2">
              <AlertTriangle size={12} />
              Resolve the above to enable manual execution.
            </div>
          )}
        </div>

        {/* To enable Autonomous mode */}
        <div className="card opacity-75">
          <div className="flex items-center gap-2 mb-3">
            <Zap size={14} className="text-gray-500" />
            <h4 className="font-medium text-sm text-gray-400">Autonomous Mode Requirements</h4>
            <Lock size={11} className="text-gray-600" />
          </div>
          <div className="space-y-2">
            {autonomousReadiness.map((item, i) => (
              <div key={i} className="flex items-start gap-2">
                {item.met ? (
                  <CheckCircle size={13} className="text-green-500 mt-0.5 flex-shrink-0" />
                ) : (
                  <XCircle size={13} className="text-gray-600 mt-0.5 flex-shrink-0" />
                )}
                <div>
                  <div className="text-xs text-gray-500">{item.label}</div>
                  {!item.met && (
                    <div className="text-[10px] text-gray-700">{item.note}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 text-xs text-gray-600 bg-gray-800/50 rounded p-2 flex items-center gap-2">
            <Lock size={11} />
            Autonomous mode is locked. Phase 3E required.
          </div>
        </div>
      </div>

      {/* Mode capability table */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
          <Shield size={14} />
          What Each Mode Permits
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-800 text-gray-500">
                <th className="text-left py-2 pr-4">Capability</th>
                <th className="text-center py-2 px-4">Observe</th>
                <th className="text-center py-2 px-4">Manual</th>
                <th className="text-center py-2 px-4 opacity-50">Autonomous</th>
              </tr>
            </thead>
            <tbody className="text-gray-400">
              {[
                ['View opportunities & evidence', true, true, true],
                ['Run preview simulations', true, true, true],
                ['Execute trades (manual confirm)', false, true, true],
                ['Autonomous execution (no confirm)', false, false, true],
                ['Global kill switch', true, true, true],
              ].map(([cap, obs, man, aut], i) => (
                <tr key={i} className="border-b border-gray-800/50">
                  <td className="py-2 pr-4">{cap as string}</td>
                  <td className="py-2 px-4 text-center">{obs ? <CheckCircle size={12} className="text-green-500 mx-auto" /> : <XCircle size={12} className="text-gray-700 mx-auto" />}</td>
                  <td className="py-2 px-4 text-center">{man ? <CheckCircle size={12} className="text-green-500 mx-auto" /> : <XCircle size={12} className="text-gray-700 mx-auto" />}</td>
                  <td className="py-2 px-4 text-center opacity-50">{aut ? <CheckCircle size={12} className="text-gray-500 mx-auto" /> : <XCircle size={12} className="text-gray-700 mx-auto" />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Demo / Dry-run context */}
      {(isDemo || isDryRun) && (
        <div className="card bg-gray-900/30 border-yellow-900/30 text-sm text-gray-400">
          <div className="flex items-start gap-2">
            <AlertTriangle size={14} className="text-yellow-500 mt-0.5 flex-shrink-0" />
            <div>
              <span className="text-yellow-400 font-medium">
                {isDemo ? 'Demo Mode' : 'Dry-Run Mode'}:{' '}
              </span>
              {isDemo
                ? 'No venue services are reachable. All execution is disconnected.'
                : 'Backend DRY_RUN=true. Orders are simulated even in Manual mode.'}
              {' '}No real capital is at risk.
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
