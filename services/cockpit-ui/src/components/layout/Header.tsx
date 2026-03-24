export function Header() {
  return (
    <header className="h-12 bg-gray-800 border-b border-gray-700 flex items-center justify-between px-4">
      <div className="flex items-center gap-4">
        <div className="text-sm text-gray-400">
          {new Date().toLocaleString()}
        </div>
        <div className="px-2 py-0.5 rounded bg-yellow-900/30 text-yellow-500 text-xs font-medium border border-yellow-900/50">
          DRY RUN MODE (Mock Execution)
        </div>
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
