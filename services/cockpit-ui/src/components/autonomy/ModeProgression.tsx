import { Eye, MousePointer2, Zap, Lock, ArrowRight } from 'lucide-react'
import type { ExecutionMode } from '../../context'

export function ModeProgression({ mode }: { mode: ExecutionMode }) {
  return (
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
  )
}
