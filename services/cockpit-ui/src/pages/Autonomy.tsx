import { AlertTriangle } from 'lucide-react'
import { useExecution } from '../context'
import { useExecutionStatus } from '../api/hooks'
import { ModeCapabilities } from '../components/autonomy/ModeCapabilities'
import { ModeProgression } from '../components/autonomy/ModeProgression'
import { ReadinessChecklists } from '../components/autonomy/ReadinessChecklists'

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

  const allVenuesConnected = (status?.venues?.length ?? 0) > 0 &&
    (status?.venues?.every(v => v.circuit_open !== 'unknown') ?? false)
  const executionEnabled = status?.execution_enabled === 'true'
  const anyCircuitOpen = status?.venues?.some(v => v.circuit_open === true)

  // Readiness checklist items per mode gate
  const manualReadiness = [
    {
      label: 'All venue exec services reachable',
      met: allVenuesConnected,
      note: 'exec-hl-svc must respond to /circuit-status'
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
      <ModeProgression mode={mode} />

      {/* Readiness Checklists */}
      <ReadinessChecklists mode={mode} manualReadiness={manualReadiness} autonomousReadiness={autonomousReadiness} />

      {/* Mode capability table */}
      <ModeCapabilities />

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
