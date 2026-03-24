import { createContext, useContext, useState, useEffect, ReactNode } from 'react'

export type ExecutionMode = 'observe' | 'manual' | 'autonomous'

interface ExecutionState {
  mode: ExecutionMode
  globalKillSwitch: boolean
  venueKillSwitches: Record<string, boolean>
  isDryRun: boolean // From backend
  isDemo: boolean // No real credentials configured
}

interface ExecutionContextValue extends ExecutionState {
  setMode: (mode: ExecutionMode) => void
  toggleGlobalKill: () => void
  toggleVenueKill: (venue: string) => void
  setBackendState: (dryRun: boolean, demo: boolean) => void
  canExecute: boolean
}

const ExecutionContext = createContext<ExecutionContextValue | null>(null)

const STORAGE_KEY = 'tradesync_execution_state'

const defaultState: ExecutionState = {
  mode: 'observe',
  globalKillSwitch: false,
  venueKillSwitches: {
    drift: false,
    hyperliquid: false
  },
  isDryRun: true,
  isDemo: true
}

export function ExecutionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ExecutionState>(() => {
    // Load from localStorage on init
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        const parsed = JSON.parse(stored)
        return { ...defaultState, ...parsed }
      }
    } catch (e) {
      console.warn('Failed to load execution state from localStorage:', e)
    }
    return defaultState
  })

  // Persist to localStorage when state changes
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        mode: state.mode,
        globalKillSwitch: state.globalKillSwitch,
        venueKillSwitches: state.venueKillSwitches
      }))
    } catch (e) {
      console.warn('Failed to save execution state to localStorage:', e)
    }
  }, [state.mode, state.globalKillSwitch, state.venueKillSwitches])

  const setMode = (mode: ExecutionMode) => {
    // Autonomous mode is locked for now
    if (mode === 'autonomous') return
    setState(prev => ({ ...prev, mode }))
  }

  const toggleGlobalKill = () => {
    setState(prev => ({ ...prev, globalKillSwitch: !prev.globalKillSwitch }))
  }

  const toggleVenueKill = (venue: string) => {
    setState(prev => ({
      ...prev,
      venueKillSwitches: {
        ...prev.venueKillSwitches,
        [venue]: !prev.venueKillSwitches[venue]
      }
    }))
  }

  const setBackendState = (isDryRun: boolean, isDemo: boolean) => {
    setState(prev => ({ ...prev, isDryRun, isDemo }))
  }

  // Can only execute if:
  // - Mode is not 'observe'
  // - Global kill switch is off
  // - (Per-venue checks happen at execution time)
  const canExecute = state.mode !== 'observe' && !state.globalKillSwitch

  return (
    <ExecutionContext.Provider value={{
      ...state,
      setMode,
      toggleGlobalKill,
      toggleVenueKill,
      setBackendState,
      canExecute
    }}>
      {children}
    </ExecutionContext.Provider>
  )
}

export function useExecution() {
  const context = useContext(ExecutionContext)
  if (!context) {
    throw new Error('useExecution must be used within ExecutionProvider')
  }
  return context
}
