import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { SkillGateResponse } from '../types'

/**
 * The skill gate, measured the corrected way: entry-time regimes, counted
 * independence, three separate verdicts. The block bootstrap makes this a
 * slow read, so it refreshes on a long interval.
 */
export function useSkillGate(symbol?: string) {
  return useQuery({
    queryKey: ['skill-gate', symbol ?? 'all'],
    queryFn: () => apiGet<SkillGateResponse>(`/state/outcomes/skill-gate${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`),
    refetchInterval: 300_000,
    staleTime: 120_000,
    retry: 1,
  })
}
