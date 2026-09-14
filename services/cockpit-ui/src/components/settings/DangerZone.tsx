import { AlertTriangle } from 'lucide-react'

export function DangerZone({ onClearCache }: { onClearCache: () => void }) {
  return (
    <div className="card border-red-900/50">
      <h3 className="text-sm font-medium text-red-400 mb-4 flex items-center gap-2">
        <AlertTriangle size={14} />
        Danger Zone
      </h3>
      <div>
        <button
          onClick={onClearCache}
          className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-sm"
        >
          Clear Local Cache
        </button>
        <p className="mt-2 text-xs text-gray-500">
          Clears cached preview results and local execution state. Page will reload.
        </p>
      </div>
    </div>
  )
}
