import { AlertTriangle, Eye, Info } from 'lucide-react'
import { useExecution } from '../context'

type BannerVariant = 'full' | 'compact' | 'inline'

interface DryRunBannerProps {
  variant?: BannerVariant
}

export function DryRunBanner({ variant = 'full' }: DryRunBannerProps) {
  const { isDryRun, isDemo, mode } = useExecution()

  // Determine what to show
  const showDryRun = isDryRun
  const showDemo = isDemo
  const showObserve = mode === 'observe'

  if (!showDryRun && !showDemo && !showObserve) {
    return null
  }

  if (variant === 'inline') {
    return (
      <div className="flex flex-wrap gap-2">
        {showObserve && (
          <span className="inline-flex items-center gap-1 text-xs bg-blue-900/50 text-blue-300 px-2 py-1 rounded">
            <Eye size={10} />
            OBSERVE MODE
          </span>
        )}
        {showDryRun && (
          <span className="inline-flex items-center gap-1 text-xs bg-yellow-900/50 text-yellow-400 px-2 py-1 rounded font-mono">
            <AlertTriangle size={10} />
            DRY_RUN
          </span>
        )}
        {showDemo && (
          <span className="inline-flex items-center gap-1 text-xs bg-gray-700 text-gray-300 px-2 py-1 rounded">
            <Info size={10} />
            DEMO
          </span>
        )}
      </div>
    )
  }

  if (variant === 'compact') {
    return (
      <div className="bg-yellow-900/20 border border-yellow-900/50 rounded p-2 flex items-center justify-center gap-3">
        {showObserve && (
          <span className="text-blue-400 text-xs font-bold flex items-center gap-1">
            <Eye size={12} />
            OBSERVE MODE
          </span>
        )}
        {showDryRun && (
          <span className="text-yellow-500 text-xs font-bold font-mono flex items-center gap-1">
            <AlertTriangle size={12} />
            DRY_RUN: NO REAL CAPITAL
          </span>
        )}
        {showDemo && !showDryRun && (
          <span className="text-gray-400 text-xs font-bold flex items-center gap-1">
            <Info size={12} />
            DEMO MODE
          </span>
        )}
      </div>
    )
  }

  // Full variant
  return (
    <div className="bg-yellow-900/20 border border-yellow-900/50 rounded-lg p-4 space-y-2">
      <div className="flex items-center gap-2 text-yellow-500">
        <AlertTriangle size={18} />
        <span className="font-bold">Simulation Mode Active</span>
      </div>
      <div className="text-sm text-yellow-300/80 space-y-1">
        {showObserve && (
          <p className="flex items-center gap-2">
            <Eye size={14} className="text-blue-400" />
            <span><strong>Observe Mode:</strong> You are in read-only mode. Switch to Manual mode to enable execution.</span>
          </p>
        )}
        {showDryRun && (
          <p className="flex items-center gap-2">
            <AlertTriangle size={14} className="text-yellow-500" />
            <span><strong>DRY_RUN=true:</strong> Orders are simulated. No actual capital will be deployed to the blockchain.</span>
          </p>
        )}
        {showDemo && (
          <p className="flex items-center gap-2">
            <Info size={14} className="text-gray-400" />
            <span><strong>Demo Mode:</strong> Venue credentials not configured. Using simulated positions and balances.</span>
          </p>
        )}
      </div>
    </div>
  )
}
