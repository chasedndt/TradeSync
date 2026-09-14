import { MousePointer2, Zap, Lock, AlertTriangle, CheckCircle, XCircle } from 'lucide-react'
import type { ExecutionMode } from '../../context'

export interface ReadinessItem {
  label: string
  met: boolean
  note: string
}

interface ReadinessChecklistsProps {
  mode: ExecutionMode
  manualReadiness: ReadinessItem[]
  autonomousReadiness: ReadinessItem[]
}

export function ReadinessChecklists({ mode, manualReadiness, autonomousReadiness }: ReadinessChecklistsProps) {
  return (
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
  )
}
