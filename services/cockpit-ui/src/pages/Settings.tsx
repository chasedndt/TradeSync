import { useState, useEffect } from 'react'
import { Key, Trash2, AlertTriangle, Check, Info, Wallet, CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { useExecutionStatus } from '../api/hooks'
import { useExecution } from '../context'

const DEFAULT_API_URL = 'http://localhost:8000'

export function Settings() {
  const [apiKey, setApiKey] = useState('')
  const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL)
  const [hasApiKey, setHasApiKey] = useState(false)
  const [saved, setSaved] = useState(false)

  const { data: execStatus, isLoading: execLoading } = useExecutionStatus()
  const { isDryRun, isDemo } = useExecution()

  useEffect(() => {
    // Load settings from localStorage
    const storedKey = localStorage.getItem('tradesync_api_key')
    const storedUrl = localStorage.getItem('tradesync_api_url')
    if (storedKey) {
      setApiKey('********') // Don't show actual key
      setHasApiKey(true)
    }
    if (storedUrl) {
      setApiUrl(storedUrl)
    }
  }, [])

  const handleSaveApiKey = () => {
    if (apiKey && apiKey !== '********') {
      localStorage.setItem('tradesync_api_key', apiKey)
      setHasApiKey(true)
      setApiKey('********')
    }
    localStorage.setItem('tradesync_api_url', apiUrl)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const handleClearApiKey = () => {
    localStorage.removeItem('tradesync_api_key')
    setApiKey('')
    setHasApiKey(false)
  }

  const handleClearCache = () => {
    // Clear react-query cache and local state
    localStorage.removeItem('tradesync_preview_cache')
    localStorage.removeItem('tradesync_execution_cache')
    window.location.reload()
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <h2 className="text-xl font-bold">Settings</h2>

      {/* API Configuration */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-400 mb-4 flex items-center gap-2">
          <Key size={14} />
          API Configuration
        </h3>

        <div className="space-y-4">
          {/* API Key */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              TradeSync Cockpit API Key
            </label>
            <div className="flex gap-2">
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Enter your API key..."
                className="input flex-1"
              />
              {hasApiKey && (
                <button
                  onClick={handleClearApiKey}
                  className="px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded text-gray-400"
                  title="Clear API Key"
                >
                  <Trash2 size={16} />
                </button>
              )}
            </div>
            <p className="mt-2 text-xs text-gray-500 flex items-start gap-1">
              <Info size={12} className="mt-0.5 flex-shrink-0" />
              <span>
                Required for /actions/* endpoints (Preview/Execute).
                Stored locally in your browser. Never sent to third parties.
              </span>
            </p>
            <div className="mt-2">
              <span className={`text-xs px-2 py-1 rounded ${hasApiKey ? 'bg-green-900/50 text-green-400' : 'bg-gray-800 text-gray-500'}`}>
                {hasApiKey ? 'Key configured' : 'No key set'}
              </span>
            </div>
          </div>

          {/* API Base URL */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              API Base URL
            </label>
            <input
              type="text"
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              placeholder="http://localhost:8000"
              className="input w-full"
            />
            <p className="mt-2 text-xs text-gray-500">
              The base URL for the TradeSync state-api backend.
            </p>
          </div>

          <button
            onClick={handleSaveApiKey}
            className="btn btn-primary flex items-center gap-2"
          >
            {saved ? <Check size={16} /> : null}
            {saved ? 'Saved!' : 'Save Settings'}
          </button>
        </div>
      </div>

      {/* Venue Connection Status */}
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
            const hasError = !!venue.error

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
                {hasError && (
                  <p className="text-xs text-red-400 mt-1">{venue.error}</p>
                )}
                {venue.fail_count != null && venue.fail_count > 0 && (
                  <p className="text-xs text-gray-500 mt-1">
                    Fail count: {venue.fail_count}
                  </p>
                )}
                {!isConnected && (
                  <p className="text-xs text-gray-500 mt-2">
                    {venue.venue === 'drift'
                      ? 'Drift requires Solana wallet connection for live trading.'
                      : 'Hyperliquid requires API keys configured via backend environment variables.'}
                  </p>
                )}
              </div>
            )
          })}

          {!execStatus?.venues?.length && !execLoading && (
            <div className="text-gray-500 text-sm">No venue data available</div>
          )}
        </div>

        {isDemo && (
          <div className="mt-4 p-3 bg-blue-900/20 border border-blue-900/50 rounded text-sm text-blue-300 flex items-start gap-2">
            <Info size={14} className="mt-0.5 flex-shrink-0" />
            <div>
              <strong>Demo Mode Active:</strong> All executions are simulated.
              Configure venue credentials to enable live trading.
            </div>
          </div>
        )}
      </div>

      {/* Danger Zone */}
      <div className="card border-red-900/50">
        <h3 className="text-sm font-medium text-red-400 mb-4 flex items-center gap-2">
          <AlertTriangle size={14} />
          Danger Zone
        </h3>

        <div className="space-y-4">
          <div>
            <button
              onClick={handleClearCache}
              className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-sm"
            >
              Clear Local Cache
            </button>
            <p className="mt-2 text-xs text-gray-500">
              Clears all cached preview results and local state. The page will reload.
            </p>
          </div>
        </div>
      </div>

      {/* Environment Info */}
      <div className="card bg-gray-900/30">
        <h3 className="text-sm font-medium text-gray-400 mb-3">Environment</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Mode:</span>
            <span className={`ml-2 ${isDemo ? 'text-yellow-400' : 'text-green-400'}`}>
              {isDemo ? 'Demo' : 'Live'}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Backend:</span>
            <span className="ml-2 text-gray-300 font-mono text-xs">{apiUrl}</span>
          </div>
          <div>
            <span className="text-gray-500">DRY_RUN:</span>
            <span className={`ml-2 ${isDryRun ? 'text-yellow-400' : 'text-green-400'}`}>
              {isDryRun ? 'Enabled' : 'Disabled'}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Execution Gate:</span>
            <span className={`ml-2 ${execStatus?.execution_enabled === 'true' ? 'text-green-400' : 'text-yellow-400'}`}>
              {execStatus?.execution_enabled === 'true' ? 'Open' : 'Closed'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
