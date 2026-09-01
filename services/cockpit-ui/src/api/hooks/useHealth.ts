import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { HealthResponse } from '../types'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => apiGet<HealthResponse>('/state/health'),
    refetchInterval: 10_000,
    retry: 1,
  })
}
