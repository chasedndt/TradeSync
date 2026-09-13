import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../client'
import type { FleetDirective, FleetDirectiveKind, FleetJobsResponse, FleetUsageResponse } from '../types'

export interface FleetDirectiveBody {
  job_id: string
  kind: FleetDirectiveKind
  preset?: string
  enabled?: boolean
  workdir?: string
  deliver?: string
}

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
 * A directive the state API applies through the Hermes gateway's jobs API at
 * once (status "applied", channel "api"). The working directory, or a schedule
 * or enabled change while the gateway is down, stays pending for the host bridge.
 */
export function useFleetDirective() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: FleetDirectiveBody) =>
      apiPost<FleetDirective>('/state/fleet/directives', { requested_by: 'operator', ...body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['fleet-jobs'] })
      qc.invalidateQueries({ queryKey: ['fleet-directives'] })
    },
  })
}
