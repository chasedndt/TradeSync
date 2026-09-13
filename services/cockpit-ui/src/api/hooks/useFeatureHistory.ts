import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'

export interface FeatureHistoryResponse {
  schema_version: 'feature_history_v1'
  symbol: string
  window: string
  /** feature id -> [unix seconds, value], oldest first */
  series: Record<string, [number, number][]>
  authority: 'display_only'
}

/** One catalog feature's recorded series over the last seven days, fetched only when its chart is open. */
export function useFeatureHistory(symbol: string, featureId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['feature-history', symbol, featureId],
    queryFn: () =>
      apiGet<FeatureHistoryResponse>(
        `/state/regime-lab/feature-history?symbol=${encodeURIComponent(symbol)}&feature_ids=${encodeURIComponent(featureId)}&window=7d&points=600`,
      ),
    enabled,
    refetchInterval: enabled ? 120_000 : false,
    staleTime: 60_000,
    retry: 1,
  })
}
