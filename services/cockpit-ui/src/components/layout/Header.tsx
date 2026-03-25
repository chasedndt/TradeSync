import { useExecution } from '../../context'

function SystemModeBadge() {
  const { isDryRun, isDemo, mode } = useExecution()

  // Priority order: demo > dry-run > observe > manual
  if (isDemo) {
    return (
      <div className="px-2 py-0.5 rounded bg-gray-800 text-gray-400 text-xs font-medium border border-gray-700">
        DEMO MODE — no venue connectivity
      </div>
    )
  }
  if (isDryRun) {
    return (
      <div className="px-2 py-0.5 rounded bg-yellow-900/30 text-yellow-500 text-xs font-medium border border-yellow-900/50">
        DRY RUN — orders simulated, no real capital
      </div>
    )
  }
  if (mode === 'observe') {
    return (
      <div className="px-2 py-0.5 rounded bg-blue-900/30 text-blue-400 text-xs font-medium border border-blue-900/50">
        OBSERVE — read-only, execution disarmed
      </div>
    )
  }
  if (mode === 'manual') {
    return (
      <div className="px-2 py-0.5 rounded bg-orange-900/30 text-orange-400 text-xs font-medium border border-orange-900/50">
        MANUAL — live execution armed
      </div>
    )
  }
  // autonomous (currently locked, but handle it)
  return (
    <div className="px-2 py-0.5 rounded bg-red-900/30 text-red-400 text-xs font-medium border border-red-900/50">
      AUTONOMOUS — live execution active
    </div>
  )
}

export function Header() {
  return (
    <header className="h-12 bg-gray-800 border-b border-gray-700 flex items-center justify-between px-4">
      <div className="flex items-center gap-4">
        <div className="text-sm text-gray-400">
          {new Date().toLocaleString()}
        </div>
        <SystemModeBadge />
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
          <span className="text-xs text-gray-400">Live Telemetry</span>
        </div>
      </div>
    </header>
  )
}
