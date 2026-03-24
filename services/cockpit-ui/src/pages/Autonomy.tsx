import { Eye, MousePointer2, Zap, Shield, Lock, AlertTriangle, CheckCircle } from 'lucide-react'

export function Autonomy() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Autonomy Control</h2>
        <span className="text-xs bg-blue-900/50 text-blue-400 px-2 py-1 rounded">
          OBSERVE MODE ACTIVE
        </span>
      </div>

      {/* Mode State Machine */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-400 mb-4">Execution Mode State Machine</h3>
        <div className="flex items-center justify-between">
          {/* Observe */}
          <div className="flex-1 text-center">
            <div className="w-16 h-16 mx-auto rounded-full bg-blue-900/30 border-2 border-blue-500 flex items-center justify-center mb-2">
              <Eye size={24} className="text-blue-500" />
            </div>
            <div className="font-bold text-blue-400">Observe</div>
            <div className="text-xs text-gray-500">Read-only</div>
          </div>

          {/* Arrow */}
          <div className="flex-shrink-0 px-4">
            <div className="w-12 h-0.5 bg-gray-700 relative">
              <div className="absolute right-0 top-1/2 -translate-y-1/2 w-0 h-0 border-t-4 border-b-4 border-l-8 border-t-transparent border-b-transparent border-l-gray-700" />
            </div>
          </div>

          {/* Manual */}
          <div className="flex-1 text-center">
            <div className="w-16 h-16 mx-auto rounded-full bg-gray-800 border-2 border-gray-600 flex items-center justify-center mb-2">
              <MousePointer2 size={24} className="text-gray-500" />
            </div>
            <div className="font-bold text-gray-400">Manual</div>
            <div className="text-xs text-gray-500">Click to confirm</div>
          </div>

          {/* Arrow */}
          <div className="flex-shrink-0 px-4">
            <div className="w-12 h-0.5 bg-gray-700 relative">
              <div className="absolute right-0 top-1/2 -translate-y-1/2 w-0 h-0 border-t-4 border-b-4 border-l-8 border-t-transparent border-b-transparent border-l-gray-700" />
            </div>
          </div>

          {/* Autonomous */}
          <div className="flex-1 text-center opacity-50">
            <div className="w-16 h-16 mx-auto rounded-full bg-gray-800 border-2 border-gray-700 flex items-center justify-center mb-2 relative">
              <Zap size={24} className="text-gray-600" />
              <Lock size={12} className="absolute -top-1 -right-1 text-gray-500" />
            </div>
            <div className="font-bold text-gray-500">Autonomous</div>
            <div className="text-xs text-gray-600">Policy-bound</div>
          </div>
        </div>
      </div>

      {/* Mode Details */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card border-blue-500 bg-blue-900/5">
          <div className="flex items-center gap-2 mb-3">
            <Eye size={16} className="text-blue-500" />
            <h4 className="font-bold text-blue-400">Observe Mode</h4>
            <span className="text-[10px] bg-blue-900/50 px-1.5 py-0.5 rounded text-blue-300">CURRENT</span>
          </div>
          <ul className="text-xs text-gray-400 space-y-2">
            <li className="flex items-start gap-2">
              <CheckCircle size={12} className="text-green-500 mt-0.5 flex-shrink-0" />
              View all opportunities and evidence
            </li>
            <li className="flex items-start gap-2">
              <CheckCircle size={12} className="text-green-500 mt-0.5 flex-shrink-0" />
              Run preview simulations
            </li>
            <li className="flex items-start gap-2">
              <AlertTriangle size={12} className="text-yellow-500 mt-0.5 flex-shrink-0" />
              Cannot execute trades
            </li>
          </ul>
        </div>

        <div className="card">
          <div className="flex items-center gap-2 mb-3">
            <MousePointer2 size={16} className="text-yellow-500" />
            <h4 className="font-bold text-gray-300">Manual Mode</h4>
          </div>
          <ul className="text-xs text-gray-400 space-y-2">
            <li className="flex items-start gap-2">
              <CheckCircle size={12} className="text-green-500 mt-0.5 flex-shrink-0" />
              Execute trades with explicit confirmation
            </li>
            <li className="flex items-start gap-2">
              <CheckCircle size={12} className="text-green-500 mt-0.5 flex-shrink-0" />
              Risk policies enforced on preview
            </li>
            <li className="flex items-start gap-2">
              <Shield size={12} className="text-blue-500 mt-0.5 flex-shrink-0" />
              Human approval required per trade
            </li>
          </ul>
        </div>

        <div className="card opacity-50">
          <div className="flex items-center gap-2 mb-3">
            <Zap size={16} className="text-red-500" />
            <h4 className="font-bold text-gray-300">Autonomous Mode</h4>
            <Lock size={12} className="text-gray-500" />
          </div>
          <ul className="text-xs text-gray-500 space-y-2">
            <li className="flex items-start gap-2">
              <AlertTriangle size={12} className="text-red-500 mt-0.5 flex-shrink-0" />
              System executes within policy bounds
            </li>
            <li className="flex items-start gap-2">
              <Shield size={12} className="text-gray-600 mt-0.5 flex-shrink-0" />
              Kill switch can halt all activity
            </li>
            <li className="flex items-start gap-2">
              <Lock size={12} className="text-gray-600 mt-0.5 flex-shrink-0" />
              Requires wallet/signing authority
            </li>
          </ul>
        </div>
      </div>

      {/* Requirements for Autonomous */}
      <div className="card border-yellow-900/50 bg-yellow-900/5">
        <h3 className="text-sm font-medium text-yellow-400 mb-3 flex items-center gap-2">
          <Lock size={14} />
          Requirements for Autonomous Mode
        </h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="flex items-center gap-2">
            <AlertTriangle size={14} className="text-yellow-500" />
            <span className="text-gray-400">Wallet connection configured</span>
          </div>
          <div className="flex items-center gap-2">
            <AlertTriangle size={14} className="text-yellow-500" />
            <span className="text-gray-400">Signing authority established</span>
          </div>
          <div className="flex items-center gap-2">
            <AlertTriangle size={14} className="text-yellow-500" />
            <span className="text-gray-400">Risk policies reviewed</span>
          </div>
          <div className="flex items-center gap-2">
            <AlertTriangle size={14} className="text-yellow-500" />
            <span className="text-gray-400">Audit trail enabled</span>
          </div>
        </div>
      </div>

      <div className="card bg-gray-900/30 text-sm text-gray-400">
        <h4 className="font-medium text-gray-300 mb-2">Phase 3E: Wallet/Signing Authority</h4>
        <p>
          Autonomous mode requires secure key management. Phase 3E introduces
          two modes: manual signing (UI prompts for wallet signature) and
          autonomous keys (server-side custody with strict limits and full audit trail).
        </p>
      </div>
    </div>
  )
}
