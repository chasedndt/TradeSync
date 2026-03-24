import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { Opportunity } from '../types'

export function useOpportunities(status = 'new', limit = 20) {
  return useQuery({
    queryKey: ['opportunities', status, limit],
    queryFn: () => apiGet<Opportunity[]>(`/state/opportunities?status=${status}&limit=${limit}`),
    refetchInterval: 5000,
  })
}
