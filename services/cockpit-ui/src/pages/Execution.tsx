import { useExecutionStatus } from '../api/hooks'
import { StatusBadge, DryRunBanner } from '../components'
import { useExecution } from '../context'
import { AlertTriangle, Eye, MousePointer2, Zap, Power, Shield, Activity } from 'lucide-react'

const modeConfig = {
  observe: {
    label: 'Observe',
    icon: Eye,
    description: 'Read-only mode. No execution capabilities.',
    color: 'text-blue-400 border-blue-500'
  },
  manual: {
    label: 'Manual',
    icon: MousePointer2,
    description: 'Requires explicit confirmation for each trade.',
    color: 'text-yellow-400 border-yellow-500'
  },
  autonomous: {
    label: 'Autonomous',
    icon: Zap,
    description: 'System executes automatically within policy bounds.',
    color: 'text-red-400 border-red-500'
  }
} as const

export function Execution() {
  const { data: status, isLoading, error } = useExecutionStatus()
  const {
    mode,
    setMode,
    globalKillSwitch,
    toggleGlobalKill,
    venueKillSwitches,
    toggleVenueKill
  } = useExecution()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Execution Control</h2>
        {globalKillSwitch && (
          <div className="flex items-center gap-2 text-red-500 animate-pulse">
            <Power size={16} />
            <span className="text-sm font-bold">KILL SWITCH ACTIVE</span>
          </div>
        )}
      </div>

      {/* Dry Run Banner */}
      <DryRunBanner variant="full" />

      {isLoading && <div className="text-gray-400">Loading...</div>}
      {error && <div className="text-red-400">Error loading execution status</div>}

      {/* Global Kill Switch */}
      <div className={`card ${globalKillSwitch ? 'border-red-500 bg-red-900/10' : 'border-gray-700'}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`p-3 rounded-lg ${globalKillSwitch ? 'bg-red-900/50' : 'bg-gray-800'}`}>
              <Power size={24} className={globalKillSwitch ? 'text-red-500' : 'text-gray-500'} />
            </div>
            <div>
              <h3 className="font-bold">Global Kill Switch</h3>
              <p className="text-sm text-gray-400">
                Emergency stop for all execution activity across all venues.
              </p>
            </div>
          </div>
          <button
            onClick={toggleGlobalKill}
            className={`px-6 py-3 rounded-lg font-bold text-sm transition-all ${
              globalKillSwitch
                ? 'bg-green-600 hover:bg-green-500 text-white'
                : 'bg-red-600 hover:bg-red-500 text-white'
            }`}
          >
            {globalKillSwitch ? 'RESUME' : 'KILL ALL'}
          </button>
        </div>
      </div>

      {/* Execution Mode */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-400 mb-4 flex items-center gap-2">
          <Shield size={14} />
          Execution Mode
        </h3>
        <div className="grid grid-cols-3 gap-4">
          {(Object.entries(modeConfig) as [keyof typeof modeConfig, typeof modeConfig['observe']][]).map(([key, config]) => {
            const Icon = config.icon
            const isActive = mode === key
            const isLocked = key === 'autonomous'

            return (
              <button
                key={key}
                onClick={() => setMode(key)}
                disabled={isLocked}
                className={`p-4 rounded-lg border-2 text-left transition-all ${
                  isActive
                    ? `${config.color} bg-gray-900`
                    : 'border-gray-700 text-gray-400 hover:border-gray-600'
                } ${isLocked ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <Icon size={18} />
                  <span className="font-bold">{config.label}</span>
                  {isLocked && (
                    <span className="text-[10px] bg-gray-700 px-1.5 py-0.5 rounded">LOCKED</span>
                  )}
                </div>
                <p className="text-xs text-gray-500">{config.description}</p>
              </button>
            )
          })}
        </div>
        <p className="mt-4 text-xs text-gray-600">
          Autonomous mode is locked pending wallet/signing authority configuration.
          Your mode selection is persisted in your browser.
        </p>
      </div>

      {status && (
        <>
          {/* Global Gate */}
          <div className="card">
            <h3 className="text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
              <Activity size={14} />
              System Status
            </h3>
            <div className="flex items-center gap-3">
              <StatusBadge status={status.execution_enabled === 'true' ? 'ok' : 'off'} />
              <span className="text-sm">
                {status.execution_enabled === 'true'
                  ? 'Backend execution is enabled'
                  : 'Backend execution is disabled (DRY_RUN mode)'}
              </span>
            </div>
            {mode === 'observe' && (
              <div className="mt-3 p-3 bg-blue-900/20 border border-blue-900/50 rounded text-sm text-blue-300">
                You are in Observe mode. Switch to Manual mode to enable execution controls.
              </div>
            )}
          </div>

          {/* Venue Kill Switches & Circuit Breakers */}
          <div className="card">
            <h3 className="text-sm font-medium text-gray-400 mb-3">Venue Controls</h3>
            <div className="space-y-3">
              {status.venues.map((venue) => {
                const isKilled = venueKillSwitches[venue.venue] || globalKillSwitch

                return (
                  <div
                    key={venue.venue}
                    className={`bg-gray-900 rounded p-4 ${isKilled ? 'border border-red-900/50' : ''}`}
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <span className="font-medium capitalize text-lg">{venue.venue}</span>
                        {isKilled && (
                          <span className="text-xs bg-red-900/50 text-red-400 px-2 py-0.5 rounded">
                            STOPPED
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => toggleVenueKill(venue.venue)}
                        disabled={globalKillSwitch}
                        className={`px-4 py-2 rounded text-xs font-bold transition-all ${
                          isKilled
                            ? 'bg-green-700 hover:bg-green-600 text-white'
                            : 'bg-red-700 hover:bg-red-600 text-white'
                        } ${globalKillSwitch ? 'opacity-50 cursor-not-allowed' : ''}`}
                      >
                        {isKilled ? 'RESUME' : 'STOP'}
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-gray-500">Circuit Breaker:</span>
                        <span className="ml-2">
                          {venue.circuit_open === true && (
                            <StatusBadge status="error" />
                          )}
                          {venue.circuit_open === false && (
                            <StatusBadge status="ok" />
                          )}
                          {venue.circuit_open === 'unknown' && (
                            <StatusBadge status="degraded" />
                          )}
                        </span>
                      </div>
                      {venue.fail_count !== undefined && (
                        <div>
                          <span className="text-gray-500">Fail count:</span>
                          <span className="ml-2 font-mono">{venue.fail_count}</span>
                        </div>
                      )}
                    </div>

                    {venue.error && (
                      <div className="mt-2 text-xs text-red-400 flex items-center gap-1">
                        <AlertTriangle size={12} />
                        {venue.error}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Decisions & Orders Log (placeholder) */}
          <div className="card">
            <h3 className="text-sm font-medium text-gray-400 mb-3">Recent Decisions & Orders</h3>
            <div className="bg-gray-900/50 border border-gray-800 border-dashed rounded-lg p-8 text-center">
              <p className="text-gray-500 text-sm">No recent execution activity.</p>
              <p className="text-gray-600 text-xs mt-2">
                Decisions and orders will appear here when trades are previewed and executed.
              </p>
            </div>
            <div className="mt-3 flex justify-end">
              <a href="/logs" className="text-xs text-blue-400 hover:underline">
                View full logs &rarr;
              </a>
            </div>
          </div>

          {/* Info */}
          <div className="card text-sm text-gray-400">
            <p>
              Circuit breakers automatically open after consecutive failures to protect
              against cascading errors. They will reset after a cooldown period.
              Kill switches provide manual emergency stops.
            </p>
          </div>
        </>
      )}
    </div>
  )
}
