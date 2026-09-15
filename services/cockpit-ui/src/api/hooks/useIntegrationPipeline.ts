import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { PipelineFeeds } from '../pipelineFeedTypes'
import type { IntegrationPipelineStatus } from '../types'

/** The pipeline's stages, and the feed heartbeats beside them (absent from a state API that predates them). */
export type IntegrationPipelineWithFeeds = IntegrationPipelineStatus & { feeds?: PipelineFeeds }

export function useIntegrationPipeline() {
  return useQuery({
    queryKey: ['integration-pipeline'],
    queryFn: () => apiGet<IntegrationPipelineWithFeeds>('/state/integration-pipeline'),
    refetchInterval: 10_000,
    retry: 1,
  })
}
