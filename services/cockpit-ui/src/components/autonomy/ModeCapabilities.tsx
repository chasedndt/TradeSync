import { Shield, CheckCircle, XCircle } from 'lucide-react'

export function ModeCapabilities() {
  return (
    <div className="card">
      <h3 className="text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
        <Shield size={14} />
        What Each Mode Permits
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-800 text-gray-500">
              <th className="text-left py-2 pr-4">Capability</th>
              <th className="text-center py-2 px-4">Observe</th>
              <th className="text-center py-2 px-4">Manual</th>
              <th className="text-center py-2 px-4 opacity-50">Autonomous</th>
            </tr>
          </thead>
          <tbody className="text-gray-400">
            {[
              ['View opportunities & evidence', true, true, true],
              ['Run preview simulations', true, true, true],
              ['Execute trades (manual confirm)', false, true, true],
              ['Autonomous execution (no confirm)', false, false, true],
              ['Global kill switch', true, true, true],
            ].map(([cap, obs, man, aut], i) => (
              <tr key={i} className="border-b border-gray-800/50">
                <td className="py-2 pr-4">{cap as string}</td>
                <td className="py-2 px-4 text-center">{obs ? <CheckCircle size={12} className="text-green-500 mx-auto" /> : <XCircle size={12} className="text-gray-700 mx-auto" />}</td>
                <td className="py-2 px-4 text-center">{man ? <CheckCircle size={12} className="text-green-500 mx-auto" /> : <XCircle size={12} className="text-gray-700 mx-auto" />}</td>
                <td className="py-2 px-4 text-center opacity-50">{aut ? <CheckCircle size={12} className="text-gray-500 mx-auto" /> : <XCircle size={12} className="text-gray-700 mx-auto" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
