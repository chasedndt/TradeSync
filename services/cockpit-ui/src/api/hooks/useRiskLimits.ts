import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { RiskLimitResponse } from '../types'

export function useRiskLimits() {
  return useQuery({
    queryKey: ['risk-limits'],
    queryFn: () => apiGet<RiskLimitResponse>('/state/risk/limits'),
    refetchInterval: 30000,
  })
}
