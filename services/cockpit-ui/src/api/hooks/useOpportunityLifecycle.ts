import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { LifecycleResponse } from '../learningTypes'

/** Live count, the last opportunity, and the scorer's refusal reasons over a recent window. */
export function useOpportunityLifecycle(windowMinutes = 60, enabled = true) {
  return useQuery({
    queryKey: ['opportunity-lifecycle', windowMinutes],
    queryFn: () => apiGet<LifecycleResponse>(`/state/opportunities/lifecycle?window_minutes=${windowMinutes}`),
    refetchInterval: 30_000,
    retry: 1,
    enabled,
  })
}
