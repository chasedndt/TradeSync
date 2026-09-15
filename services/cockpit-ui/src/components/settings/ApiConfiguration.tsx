import { Key, Trash2, Info, Check } from 'lucide-react'

interface ApiConfigurationProps {
  apiKeyInput: string
  onApiKeyInputChange: (value: string) => void
  hasApiKey: boolean
  onClearKey: () => void
  apiUrl: string
  onApiUrlChange: (value: string) => void
  saved: boolean
  onSave: () => void
}

export function ApiConfiguration({
  apiKeyInput,
  onApiKeyInputChange,
  hasApiKey,
  onClearKey: handleClearKey,
  apiUrl,
  onApiUrlChange,
  saved,
  onSave: handleSave,
}: ApiConfigurationProps) {
  return (
    <div className="card">
      <h3 className="text-sm font-medium text-gray-400 mb-4 flex items-center gap-2">
        <Key size={14} />
        API Configuration
      </h3>

      <div className="space-y-4">
        {/* Mobile alert control key */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Mobile alert control key
          </label>
          <div className="flex gap-2">
            <input
              type="password"
              autoComplete="off"
              value={apiKeyInput}
              onChange={(e) => onApiKeyInputChange(e.target.value)}
              placeholder="Enter the mobile alert control key..."
              className="input flex-1"
            />
            {hasApiKey && (
              <button
                onClick={handleClearKey}
                className="px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded text-gray-400"
                title="Clear the mobile alert control key"
              >
                <Trash2 size={16} />
              </button>
            )}
          </div>
          <p className="mt-2 text-xs text-gray-500 flex items-start gap-1">
            <Info size={12} className="mt-0.5 flex-shrink-0" />
            <span>
              Sent as X-API-Key to this Cockpit&apos;s state-api, which checks it only on the mobile alert controls
              (MOBILE_ALERTS_CONTROL_KEY). Kept for this browser session only.
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
            onChange={(e) => onApiUrlChange(e.target.value)}
            placeholder="/api"
            className="input w-full"
          />
          <p className="mt-2 text-xs text-gray-500">
            The base URL for the TradeSync state-api. Default is <code className="text-gray-400">/api</code> (proxied by nginx inside Docker).
            Only a path on this site or a loopback address such as <code className="text-gray-400">http://127.0.0.1:8000</code> is used;
            anything else falls back to <code className="text-gray-400">/api</code>, so credentials never go to another host.
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
  )
}
