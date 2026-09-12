import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { ThesisResponse } from '../types'

/**
 * The SOP's minimum valid thesis for one symbol, assembled server-side from
 * measured evidence. It embeds the skill gate and evidence cards, so it is a
 * slow read; one minute keeps the freshness line honest without hammering
 * the bootstrap.
 */
export function useThesis(symbol: string) {
  return useQuery({
    queryKey: ['thesis', symbol],
    queryFn: () => apiGet<ThesisResponse>(`/state/thesis?symbol=${encodeURIComponent(symbol)}`),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 1,
  })
}
