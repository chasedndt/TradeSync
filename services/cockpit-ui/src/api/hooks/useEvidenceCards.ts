import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { EvidenceCardsReading } from '../outcomeEvidenceTypes'

/**
 * One card per candidate feature: what its sign at entry earned against
 * measured outcomes. Served from the API's measured cache like the skill gate;
 * while a market is first measured the reading says "computing" and is asked
 * for again every few seconds.
 */
export function useEvidenceCards(symbol?: string) {
  return useQuery({
    queryKey: ['evidence-cards', symbol ?? 'all'],
    queryFn: () => apiGet<EvidenceCardsReading>(`/state/outcomes/evidence-cards${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`),
    refetchInterval: (query) => (query.state.data?.status === 'computing' ? 5_000 : 300_000),
    staleTime: 60_000,
    retry: 1,
  })
}
