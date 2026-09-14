import type { ExecutionStatus } from '../../api/types'

interface SystemMode {
  label: string
  color: string
  note: string
}

interface RuntimeEnvironmentProps {
  systemMode: SystemMode
  execStatus?: ExecutionStatus
  apiUrl: string
}

export function RuntimeEnvironment({ systemMode, execStatus, apiUrl }: RuntimeEnvironmentProps) {
  return (
    <div className="card bg-gray-900/30">
      <h3 className="text-sm font-medium text-gray-400 mb-3">Runtime Environment</h3>
      <div className="space-y-3 text-sm">
        <div className="flex items-start justify-between">
          <span className="text-gray-500">System Mode</span>
          <div className="text-right">
            <span className={`font-medium ${systemMode.color}`}>{systemMode.label}</span>
            <div className="text-xs text-gray-600 mt-0.5">{systemMode.note}</div>
          </div>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Backend Execution Gate</span>
          <span className={execStatus?.execution_enabled === 'true' ? 'text-green-400' : 'text-yellow-400'}>
            {execStatus?.execution_enabled === 'true' ? 'Open (EXECUTION_ENABLED=true)' : 'Closed (DRY_RUN active)'}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">API Base URL</span>
          <span className="text-gray-300 font-mono text-xs">{apiUrl || '/api'}</span>
        </div>
        <div className="p-2 bg-gray-800/50 rounded text-xs text-gray-500 mt-2">
          <strong className="text-gray-400">Note:</strong> System Mode and Execution Gate are independent.
          Gate = server-side env switch. Mode = client-side authority level.
          Both must permit execution before any order is submitted.
        </div>
      </div>
    </div>
  )
}
