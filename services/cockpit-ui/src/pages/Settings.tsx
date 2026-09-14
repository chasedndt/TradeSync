import { useState, useEffect } from 'react'
import { MobileAlerts } from '../components/MobileAlerts'
import { useExecutionStatus } from '../api/hooks'
import { useExecution } from '../context'
// Import client helpers so Settings and the HTTP client use the SAME localStorage keys.
// Previously Settings wrote to 'tradesync_api_key'/'tradesync_api_url' while client.ts
// read 'apiKey'/'apiBaseUrl' — configured keys were silently ignored by all API calls.
import { setApiKey, clearApiKey, setApiBaseUrl, getApiBaseUrl } from '../api/client'
import { ApiConfiguration } from '../components/settings/ApiConfiguration'
import { DangerZone } from '../components/settings/DangerZone'
import { RuntimeEnvironment } from '../components/settings/RuntimeEnvironment'
import { VenueStatus } from '../components/settings/VenueStatus'

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

      <MobileAlerts />

      {/* API Configuration */}
      <ApiConfiguration
        apiKeyInput={apiKeyInput}
        onApiKeyInputChange={setApiKeyInput}
        hasApiKey={hasApiKey}
        onClearKey={handleClearKey}
        apiUrl={apiUrl}
        onApiUrlChange={setApiUrl}
        saved={saved}
        onSave={handleSave}
      />

      {/* Venue Connection Status */}
      <VenueStatus execStatus={execStatus} execLoading={execLoading} />

      {/* Danger Zone */}
      <DangerZone onClearCache={handleClearCache} />

      {/* Environment Info — 3-state truthful display */}
      <RuntimeEnvironment systemMode={systemMode} execStatus={execStatus} apiUrl={apiUrl} />
    </div>
  )
}
