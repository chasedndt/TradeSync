import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../client'
import type { FleetDirective, FleetJobsResponse, FleetUsageResponse } from '../types'

/** The Hermes fleet as the host bridge last reported it. */
export function useFleetJobs() {
  return useQuery({
    queryKey: ['fleet-jobs'],
    queryFn: () => apiGet<FleetJobsResponse>('/state/fleet/jobs'),
    refetchInterval: 60_000,
    retry: 1,
  })
}

/** Token usage and run counts over a window, from the fleet's own audit. */
export function useFleetUsage(days = 7) {
  return useQuery({
    queryKey: ['fleet-usage', days],
    queryFn: () => apiGet<FleetUsageResponse>(`/state/fleet/usage?days=${days}`),
    refetchInterval: 120_000,
    retry: 1,
  })
}

export function useFleetDirectives(limit = 50) {
  return useQuery({
    queryKey: ['fleet-directives', limit],
    queryFn: () => apiGet<{ directives: FleetDirective[] }>(`/state/fleet/directives?limit=${limit}`),
    refetchInterval: 30_000,
    retry: 1,
  })
}

/**
 * A directive is a request to the bridge, not a change: it stays pending
 * until the bridge applies it to the fleet's registry and reports back.
 */
export function useFleetDirective() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { job_id: string; kind: 'set_schedule' | 'set_enabled' | 'set_workdir'; preset?: string; enabled?: boolean; workdir?: string }) =>
      apiPost<FleetDirective>('/state/fleet/directives', { requested_by: 'operator', ...body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['fleet-jobs'] })
      qc.invalidateQueries({ queryKey: ['fleet-directives'] })
    },
  })
}
