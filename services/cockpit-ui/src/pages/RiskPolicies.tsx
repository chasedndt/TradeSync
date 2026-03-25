import { useRiskLimits } from '../api/hooks'

export function RiskPolicies() {
  const { data: limits, isLoading, error } = useRiskLimits()

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">Risk Policies</h2>

      {isLoading && <div className="text-gray-400">Loading...</div>}
      {error && <div className="text-red-400">Error loading risk limits</div>}

      {limits && (
        <>
          {/* Current Limits */}
          <div className="card">
            <h3 className="text-sm font-medium text-gray-400 mb-3">Current Limits</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
              <div>
                <div className="text-gray-400">Max Leverage</div>
                <div className="text-xl font-bold">{limits.max_leverage}x</div>
              </div>
              <div>
                <div className="text-gray-400">Min Quality</div>
                <div className="text-xl font-bold">{(limits.min_quality * 100).toFixed(0)}%</div>
              </div>
              <div>
                <div className="text-gray-400">Max Open Positions</div>
                <div className="text-xl font-bold">{limits.max_open_positions}</div>
              </div>
              <div>
                <div className="text-gray-400">Min Size</div>
                <div className="text-xl font-bold">${limits.min_size_usd}</div>
              </div>
              <div>
                <div className="text-gray-400">Max Event Age</div>
                <div className="text-xl font-bold">{limits.max_event_age}s</div>
              </div>
              <div>
                <div className="text-gray-400">Max Signal Age</div>
                <div className="text-xl font-bold">{limits.max_signal_age}s</div>
              </div>
            </div>
          </div>

          {/* Daily Notional */}
          <div className="card">
            <h3 className="text-sm font-medium text-gray-400 mb-3">Daily Notional</h3>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Limit</span>
                <span>${limits.daily_notional_limit.toLocaleString()}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Used Today</span>
                <span>${limits.current_counters.daily_notional_usage.toLocaleString()}</span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2">
                <div
                  className="bg-blue-600 h-2 rounded-full"
                  style={{
                    width: `${Math.min(
                      100,
                      (limits.current_counters.daily_notional_usage / limits.daily_notional_limit) * 100
                    )}%`,
                  }}
                />
              </div>
              <div className="text-xs text-gray-400">
                Date: {limits.current_counters.today_date}
              </div>
            </div>
          </div>

          {/* Blacklist */}
          <div className="card">
            <h3 className="text-sm font-medium text-gray-400 mb-3">Blacklisted Symbols</h3>
            {limits.blacklist.length === 0 ? (
              <div className="text-gray-500 text-sm">No blacklisted symbols</div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {limits.blacklist.map((symbol) => (
                  <span
                    key={symbol}
                    className="px-2 py-1 bg-red-900 text-red-200 rounded text-sm"
                  >
                    {symbol}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Info */}
          <div className="card text-sm text-gray-400 space-y-2">
            <p>
              These policies are enforced by the RiskGuardian on every preview and execute call.
              They are read-only here — edit the corresponding environment variables and restart the service to change them.
            </p>
            <div className="font-mono text-xs bg-gray-900 rounded p-3 space-y-1 text-gray-500">
              <div>MAX_LEVERAGE=<span className="text-gray-400">{limits.max_leverage}</span></div>
              <div>MIN_QUALITY_THRESHOLD=<span className="text-gray-400">{limits.min_quality}</span></div>
              <div>MAX_OPEN_POSITIONS=<span className="text-gray-400">{limits.max_open_positions}</span></div>
              <div>MIN_SIZE_USD=<span className="text-gray-400">{limits.min_size_usd}</span></div>
              <div>MAX_EVENT_AGE_SECONDS=<span className="text-gray-400">{limits.max_event_age}</span></div>
              <div>MAX_SIGNAL_AGE_SECONDS=<span className="text-gray-400">{limits.max_signal_age}</span></div>
              <div>DAILY_NOTIONAL_LIMIT=<span className="text-gray-400">{limits.daily_notional_limit}</span></div>
            </div>
            <p className="text-xs text-gray-600">
              Editable policy UI (without restart) is planned for a future release.
            </p>
          </div>
        </>
      )}
    </div>
  )
}
