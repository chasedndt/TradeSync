import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { EvidenceCardsResponse } from '../types'

/**
 * One card per candidate feature: what its sign at entry earned against
 * measured outcomes. Shares the skill gate's costs and bootstrap, so it is a
 * slow read and refreshes on the same long interval.
 */
export function useEvidenceCards(symbol?: string) {
  return useQuery({
    queryKey: ['evidence-cards', symbol ?? 'all'],
    queryFn: () => apiGet<EvidenceCardsResponse>(`/state/outcomes/evidence-cards${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`),
    refetchInterval: 300_000,
    staleTime: 120_000,
    retry: 1,
  })
}
