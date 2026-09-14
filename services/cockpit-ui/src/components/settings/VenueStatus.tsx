import { Wallet, Loader2, XCircle, CheckCircle2, AlertTriangle } from 'lucide-react'
import type { ExecutionStatus } from '../../api/types'

export function VenueStatus({ execStatus, execLoading }: { execStatus?: ExecutionStatus; execLoading: boolean }) {
  return (
    <div className="card">
      <h3 className="text-sm font-medium text-gray-400 mb-4 flex items-center gap-2">
        <Wallet size={14} />
        Venue Connection Status
        {execLoading && <Loader2 size={14} className="animate-spin" />}
      </h3>

      <div className="space-y-4">
        {execStatus?.venues?.map((venue) => {
          const isConnected = venue.circuit_open !== 'unknown'
          const circuitOpen = venue.circuit_open === true

          return (
            <div key={venue.venue} className="bg-gray-900 rounded p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium capitalize">{venue.venue}</span>
                <div className="flex items-center gap-2">
                  {isConnected ? (
                    circuitOpen ? (
                      <span className="text-xs bg-red-900/50 text-red-400 px-2 py-1 rounded flex items-center gap-1">
                        <XCircle size={10} />
                        CIRCUIT OPEN
                      </span>
                    ) : (
                      <span className="text-xs bg-green-900/50 text-green-400 px-2 py-1 rounded flex items-center gap-1">
                        <CheckCircle2 size={10} />
                        CONNECTED
                      </span>
                    )
                  ) : (
                    <span className="text-xs bg-yellow-900/50 text-yellow-400 px-2 py-1 rounded flex items-center gap-1">
                      <AlertTriangle size={10} />
                      NOT CONNECTED
                    </span>
                  )}
                </div>
              </div>
              {venue.error && (
                <p className="text-xs text-red-400 mt-1">{venue.error}</p>
              )}
              {venue.fail_count != null && venue.fail_count > 0 && (
                <p className="text-xs text-gray-500 mt-1">Fail count: {venue.fail_count}</p>
              )}
              {!isConnected && (
                <p className="text-xs text-gray-500 mt-2">
                  Hyperliquid requires API keys configured via backend environment variables.
                </p>
              )}
            </div>
          )
        })}

        {!execStatus?.venues?.length && !execLoading && (
          <div className="text-gray-500 text-sm">No venue data available — exec services may be offline.</div>
        )}
      </div>
    </div>
  )
}
