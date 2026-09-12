import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../client'
import type { RehearsalListResponse, RehearseRequest, RehearseResponse } from '../types'

/** The paper rehearsal journal: every simulated fill and every refusal. */
export function useRehearsals(limit = 25) {
  return useQuery({
    queryKey: ['rehearsals', limit],
    queryFn: () => apiGet<RehearsalListResponse>(`/state/rehearsals?limit=${limit}`),
    refetchInterval: 15_000,
    retry: 1,
  })
}

/**
 * Rehearse one opportunity. Runs the per-symbol risk rules, prices a
 * simulated fill from the live mark, and journals the result. It cannot place
 * an order: the endpoint has no path to an execution service.
 */
export function useRehearse() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (req: RehearseRequest) => apiPost<RehearseResponse>('/actions/rehearse', req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rehearsals'] })
    },
  })
}
