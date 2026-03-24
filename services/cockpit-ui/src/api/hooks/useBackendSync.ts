import { useEffect } from 'react'
import { useExecutionStatus } from './useExecutionStatus'
import { useExecution } from '../../context'

/**
 * Hook that syncs the ExecutionContext with backend state.
 * Fetches execution status and updates isDryRun/isDemo accordingly.
 */
export function useBackendSync() {
  const { data: status } = useExecutionStatus()
  const { setBackendState } = useExecution()

  useEffect(() => {
    if (status) {
      // execution_enabled === "true" means DRY_RUN=false (live mode)
      const isDryRun = status.execution_enabled !== 'true'

      // Check if any venue is in "unknown" state (no response) to determine demo mode
      const hasUnknownVenues = status.venues?.some(
        (v) => v.circuit_open === 'unknown'
      )

      // Demo mode: either all venues are unknown OR execution is disabled
      const isDemo = hasUnknownVenues || isDryRun

      setBackendState(isDryRun, isDemo)
    }
  }, [status, setBackendState])

  return status
}
