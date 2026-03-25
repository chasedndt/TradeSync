import { useState, useEffect } from 'react'
import { Key, Trash2, AlertTriangle, Check, Info, Wallet, CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { useExecutionStatus } from '../api/hooks'
import { useExecution } from '../context'
// Import client helpers so Settings and the HTTP client use the SAME localStorage keys.
// Previously Settings wrote to 'tradesync_api_key'/'tradesync_api_url' while client.ts
// read 'apiKey'/'apiBaseUrl' — configured keys were silently ignored by all API calls.
import { setApiKey, clearApiKey, setApiBaseUrl, getApiBaseUrl } from '../api/client'

export function Settings() {
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [apiUrl, setApiUrl] = useState('')
  const [hasApiKey, setHasApiKey] = useState(false)
  const [saved, setSaved] = useState(false)

  const { data: execStatus, isLoading: execLoading } = useExecutionStatus()
  const { isDryRun, isDemo } = useExecution()

  useEffect(() => {
    // Load from the canonical localStorage keys used by client.ts
    const storedKey = localStorage.getItem('apiKey')
    const storedUrl = getApiBaseUrl()
    if (storedKey) {
      setApiKeyInput('••••••••') // Mask — never show actual key
      setHasApiKey(true)
    }
    setApiUrl(storedUrl)
  }, [])

  const handleSave = () => {
    // Persist via client helpers so keys are consistent across the app
    if (apiKeyInput && apiKeyInput !== '••••••••') {
      setApiKey(apiKeyInput)
      setApiKeyInput('••••••••')
      setHasApiKey(true)
    }
    setApiBaseUrl(apiUrl)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const handleClearKey = () => {
    clearApiKey()
    setApiKeyInput('')
    setHasApiKey(false)
  }

  const handleClearCache = () => {
    localStorage.removeItem('tradesync_preview_cache')
    localStorage.removeItem('tradesync_execution_cache')
    window.location.reload()
  }

  // Three-state system mode — more truthful than binary Live/Demo
  const systemMode = isDemo
    ? { label: 'DEMO', color: 'text-gray-400', note: 'No venue connectivity. All data disconnected.' }
    : isDryRun
      ? { label: 'PAPER (DRY RUN)', color: 'text-yellow-400', note: 'Orders simulated. DRY_RUN=true on backend.' }
      : { label: 'LIVE', color: 'text-green-400', note: 'Live execution enabled.' }

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
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder="Enter your API key..."
                className="input flex-1"
              />
              {hasApiKey && (
                <button
                  onClick={handleClearKey}
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
                Stored locally in your browser only. Never sent to third parties.
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
              placeholder="/api"
              className="input w-full"
            />
            <p className="mt-2 text-xs text-gray-500">
              The base URL for the TradeSync state-api. Default is <code className="text-gray-400">/api</code> (proxied by nginx inside Docker).
              Override only if accessing the API directly (e.g. <code className="text-gray-400">http://localhost:8000</code>).
            </p>
          </div>

          <button
            onClick={handleSave}
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
                    {venue.venue === 'drift'
                      ? 'Drift requires Solana wallet connection for live trading (Phase 3E).'
                      : 'Hyperliquid requires API keys configured via backend environment variables.'}
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

      {/* Danger Zone */}
      <div className="card border-red-900/50">
        <h3 className="text-sm font-medium text-red-400 mb-4 flex items-center gap-2">
          <AlertTriangle size={14} />
          Danger Zone
        </h3>
        <div>
          <button
            onClick={handleClearCache}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-sm"
          >
            Clear Local Cache
          </button>
          <p className="mt-2 text-xs text-gray-500">
            Clears cached preview results and local execution state. Page will reload.
          </p>
        </div>
      </div>

      {/* Environment Info — 3-state truthful display */}
      <div className="card bg-gray-900/30">
        <h3 className="text-sm font-medium text-gray-400 mb-3">Runtime Environment</h3>
        <div className="space-y-3 text-sm">
          <div className="flex items-start justify-between">
            <span className="text-gray-500">System Mode</span>
            <div className="text-right">
              <span className={`font-medium ${systemMode.color}`}>{systemMode.label}</span>
              <div className="text-xs text-gray-600 mt-0.5">{systemMode.note}</div>
            </div>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Backend Execution Gate</span>
            <span className={execStatus?.execution_enabled === 'true' ? 'text-green-400' : 'text-yellow-400'}>
              {execStatus?.execution_enabled === 'true' ? 'Open (EXECUTION_ENABLED=true)' : 'Closed (DRY_RUN active)'}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">API Base URL</span>
            <span className="text-gray-300 font-mono text-xs">{apiUrl || '/api'}</span>
          </div>
          <div className="p-2 bg-gray-800/50 rounded text-xs text-gray-500 mt-2">
            <strong className="text-gray-400">Note:</strong> System Mode and Execution Gate are independent.
            Gate = server-side env switch. Mode = client-side authority level.
            Both must permit execution before any order is submitted.
          </div>
        </div>
      </div>
    </div>
  )
}
