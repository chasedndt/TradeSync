import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { SkillGateReading } from '../outcomeEvidenceTypes'

/**
 * The skill gate, measured the corrected way: entry-time regimes, counted
 * independence, three separate verdicts. The API measures it behind the
 * request and serves it from memory; while a market is measured for the first
 * time the reading says "computing" and is asked for again every few seconds.
 */
export function useSkillGate(symbol?: string) {
  return useQuery({
    queryKey: ['skill-gate', symbol ?? 'all'],
    queryFn: () => apiGet<SkillGateReading>(`/state/outcomes/skill-gate${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`),
    refetchInterval: (query) => (query.state.data?.status === 'computing' ? 5_000 : 300_000),
    staleTime: 60_000,
    retry: 1,
  })
}
