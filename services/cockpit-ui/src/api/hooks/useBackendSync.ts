import { useEffect } from 'react'
import { useExecutionStatus } from './useExecutionStatus'
import { useExecution } from '../../context'

/**
 * Syncs ExecutionContext with backend state.
 *
 * paperOnly is true whenever the backend execution gate is closed
 * (EXECUTION_ENABLED is not "true"): any order goes to the paper ledger. Venue
 * reachability is reported where it is measured (Settings, Autonomy) and never
 * relabels the rest of the interface; an unknown circuit state says nothing
 * about what kind of data the Cockpit is showing.
 */
export function useBackendSync() {
  const { data: status } = useExecutionStatus()
  const { setBackendState } = useExecution()

  useEffect(() => {
    if (status) {
      setBackendState(status.execution_enabled !== 'true')
    }
  }, [status, setBackendState])

  return status
}
