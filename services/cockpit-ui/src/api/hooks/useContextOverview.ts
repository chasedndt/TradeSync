import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { ContextOverviewResponse } from '../types'

export function useContextOverview() {
  return useQuery({
    queryKey: ['context', 'overview'],
    queryFn: () => apiGet<ContextOverviewResponse>('/state/context/overview'),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 1,
  })
}
