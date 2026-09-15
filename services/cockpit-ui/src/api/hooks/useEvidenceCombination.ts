import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { EvidenceCombinationReading } from '../evidenceCombinationTypes'

/**
 * Evidence combination at one horizon: sources combined by their measured
 * likelihood ratios, scored on the newest decisions. The API measures it behind
 * the request and serves it from memory; while a horizon is measured for the
 * first time the reading says "computing" and is asked for again every few
 * seconds. The key starts with 'learning' so a learning action refreshes it too.
 */
export function useEvidenceCombination(horizon: number) {
  return useQuery({
    queryKey: ['learning', 'evidence-combination', horizon],
    queryFn: () => apiGet<EvidenceCombinationReading>(`/state/research/evidence-combination?horizon=${horizon}`),
    refetchInterval: (query) => (query.state.data?.status === 'computing' ? 5_000 : 300_000),
    staleTime: 60_000,
    retry: 1,
  })
}
