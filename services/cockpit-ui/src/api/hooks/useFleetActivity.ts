import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { FleetActivityResponse, FleetJobOutputs, FleetOutputText } from '../fleetActivityTypes'

/**
 * Every job's runs and latest stored output. The fleet bridge posts runs every
 * five minutes and the output bridge every two, so a minute's polling keeps up;
 * every row the page shows carries the time it was read.
 */
export function useFleetActivity() {
  return useQuery({
    queryKey: ['fleet-activity'],
    queryFn: () => apiGet<FleetActivityResponse>('/state/fleet/activity?runs=5'),
    refetchInterval: 60_000,
    retry: 1,
  })
}

/** One job's recent stored outputs, for the output drawer. */
export function useFleetJobOutputs(jobId: string | null) {
  return useQuery({
    queryKey: ['fleet-job-outputs', jobId],
    queryFn: () => apiGet<FleetJobOutputs>(`/state/fleet/jobs/${encodeURIComponent(jobId ?? '')}/outputs`),
    enabled: Boolean(jobId),
    retry: 1,
  })
}

/** One stored output's full text; a stored output never changes, so it is read once. */
export function useFleetOutput(outputId: string | null) {
  return useQuery({
    queryKey: ['fleet-output', outputId],
    queryFn: () => apiGet<FleetOutputText>(`/state/fleet/outputs/${encodeURIComponent(outputId ?? '')}`),
    enabled: Boolean(outputId),
    staleTime: Infinity,
    retry: 1,
  })
}
