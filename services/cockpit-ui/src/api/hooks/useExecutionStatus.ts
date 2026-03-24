import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { ExecutionStatus } from '../types'

export function useExecutionStatus() {
  return useQuery({
    queryKey: ['execution-status'],
    queryFn: () => apiGet<ExecutionStatus>('/state/execution/status'),
    refetchInterval: 10000,
  })
}
