import { useState, useEffect } from 'react'
import { MobileAlerts } from '../components/MobileAlerts'
import { useExecutionStatus } from '../api/hooks'
import { useExecution } from '../context'
// The same module the HTTP client reads, so a key entered here is the key requests carry.
import { clearMobileControlKey, getApiBaseUrl, getMobileControlKey, setApiBaseUrl, setMobileControlKey } from '../api/credentials'
import { ApiConfiguration } from '../components/settings/ApiConfiguration'
import { DangerZone } from '../components/settings/DangerZone'
import { OperatorAccess } from '../components/settings/OperatorAccess'
import { RuntimeEnvironment } from '../components/settings/RuntimeEnvironment'
import { VenueStatus } from '../components/settings/VenueStatus'

export function Settings() {
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [apiUrl, setApiUrl] = useState('')
  const [hasApiKey, setHasApiKey] = useState(false)
  const [saved, setSaved] = useState(false)

  const { data: execStatus, isLoading: execLoading } = useExecutionStatus()
  const { paperOnly } = useExecution()

  useEffect(() => {
    if (getMobileControlKey()) {
      setApiKeyInput('••••••••') // Mask — never show actual key
      setHasApiKey(true)
    }
    setApiUrl(getApiBaseUrl())
  }, [])

  const handleSave = () => {
    if (apiKeyInput && apiKeyInput !== '••••••••') {
      setMobileControlKey(apiKeyInput)
      setApiKeyInput('••••••••')
      setHasApiKey(true)
    }
    // Shows the base URL that will actually be used; one pointing at another host is not kept.
    setApiUrl(setApiBaseUrl(apiUrl))
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const handleClearKey = () => {
    clearMobileControlKey()
    setApiKeyInput('')
    setHasApiKey(false)
  }

  const handleClearCache = () => {
    localStorage.removeItem('tradesync_preview_cache')
    localStorage.removeItem('tradesync_execution_cache')
    window.location.reload()
  }

  // What the backend execution gate allows right now
  const systemMode = paperOnly
    ? { label: 'PAPER', color: 'text-yellow-400', note: 'Execution: not connected. Orders are recorded to the paper ledger.' }
    : { label: 'LIVE', color: 'text-green-400', note: 'Live execution enabled.' }

  return (
    <div className="space-y-6 max-w-2xl">
      <h2 className="text-xl font-bold">Settings</h2>

      <MobileAlerts />

      {/* Operator token and the access policy state-api enforces */}
      <OperatorAccess />

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

      {/* Environment Info */}
      <RuntimeEnvironment systemMode={systemMode} execStatus={execStatus} apiUrl={apiUrl} />
    </div>
  )
}
