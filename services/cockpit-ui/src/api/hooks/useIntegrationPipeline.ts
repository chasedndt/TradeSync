import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { IntegrationPipelineStatus } from '../types'

export function useIntegrationPipeline() {
  return useQuery({
    queryKey: ['integration-pipeline'],
    queryFn: () => apiGet<IntegrationPipelineStatus>('/state/integration-pipeline'),
    refetchInterval: 10_000,
    retry: 1,
  })
}
