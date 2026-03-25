import { useEffect } from 'react'
import { useExecutionStatus } from './useExecutionStatus'
import { useExecution } from '../../context'

/**
 * Syncs ExecutionContext with backend state.
 *
 * State semantics:
 *   isDemo   = ALL venues are unreachable (no connectivity whatsoever).
 *              The system has no real market access. All data is disconnected.
 *   isDryRun = Backend has EXECUTION_ENABLED=false (DRY_RUN mode).
 *              Orders are simulated even if venues are reachable.
 *
 * These are INDEPENDENT states. Both can be true (unreachable + dry-run).
 * Positions will show: DEMO > PAPER > LIVE in priority order.
 */
export function useBackendSync() {
  const { data: status } = useExecutionStatus()
  const { setBackendState } = useExecution()

  useEffect(() => {
    if (status) {
      // execution_enabled === "true" means DRY_RUN=false on the backend
      const isDryRun = status.execution_enabled !== 'true'

      // isDemo = ALL venues are unknown (no exec service responding at all)
      // A single unreachable venue should NOT flip the entire UI into demo mode;
      // that would hide valid data from the functioning venue.
      const allVenuesUnknown =
        !status.venues?.length ||
        status.venues.every((v) => v.circuit_open === 'unknown')

      const isDemo = allVenuesUnknown

      setBackendState(isDryRun, isDemo)
    }
  }, [status, setBackendState])

  return status
}
