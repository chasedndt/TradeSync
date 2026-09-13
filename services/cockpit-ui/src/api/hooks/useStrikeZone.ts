import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { ForwardTestResponse, LabHealthResponse, LedgerResponse, LedgerView, ScorecardsResponse } from '../strikezoneTypes'

/** The forward-test matrix, totals and paper equity. The bridge posts every five minutes. */
export function useForwardTest() {
  return useQuery({
    queryKey: ['sz-forward-test'],
    queryFn: () => apiGet<ForwardTestResponse>('/state/strikezone/forward-test'),
    refetchInterval: 60_000,
    retry: 1,
  })
}

export interface LedgerFilters {
  asset: string
  timeframe: string
  view: LedgerView
  limit: number
}

/** The signal ledger, filtered; the previous page stays on screen while a new filter loads. */
export function useLedger(filters: LedgerFilters) {
  const params = new URLSearchParams({ view: filters.view, limit: String(filters.limit) })
  if (filters.asset) params.set('asset', filters.asset)
  if (filters.timeframe) params.set('timeframe', filters.timeframe)
  return useQuery({
    queryKey: ['sz-ledger', filters],
    queryFn: () => apiGet<LedgerResponse>(`/state/strikezone/ledger?${params.toString()}`),
    refetchInterval: 60_000,
    placeholderData: keepPreviousData,
    retry: 1,
  })
}

/** Daily scorecards and regime cohorts; they change once a day. */
export function useLabScorecards() {
  return useQuery({
    queryKey: ['sz-scorecards'],
    queryFn: () => apiGet<ScorecardsResponse>('/state/strikezone/scorecards'),
    refetchInterval: 300_000,
    staleTime: 120_000,
    retry: 1,
  })
}

/** The lab's integrity report, its jobs with their causes, and the fleet inspector's standing issues. */
export function useLabHealth() {
  return useQuery({
    queryKey: ['sz-health'],
    queryFn: () => apiGet<LabHealthResponse>('/state/strikezone/health'),
    refetchInterval: 60_000,
    retry: 1,
  })
}
