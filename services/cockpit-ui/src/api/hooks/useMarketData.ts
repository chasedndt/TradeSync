import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { MarketSnapshot, MarketAlert, MarketDataStatus } from '../types'

const REFETCH_INTERVAL = 5000 // 5 seconds

export function useMarketSnapshots() {
  return useQuery({
    queryKey: ['market', 'snapshots'],
    queryFn: () => apiGet<{ snapshots: MarketSnapshot[]; count: number }>('/state/market/snapshots'),
    refetchInterval: REFETCH_INTERVAL,
    retry: 2,
  })
}

export function useMarketSnapshot(venue: string, symbol: string) {
  return useQuery({
    queryKey: ['market', 'snapshot', venue, symbol],
    queryFn: () => apiGet<MarketSnapshot>(`/state/market/snapshot?venue=${venue}&symbol=${symbol}`),
    refetchInterval: REFETCH_INTERVAL,
    retry: 2,
    enabled: !!venue && !!symbol,
  })
}

export function useMarketTimeseries(
  venue: string,
  symbol: string,
  metric: string,
  window: string = '1h'
) {
  return useQuery({
    queryKey: ['market', 'timeseries', venue, symbol, metric, window],
    queryFn: () =>
      apiGet<{
        venue: string
        symbol: string
        metric: string
        window: string
        data: Array<{ ts: number; value: number }>
        count: number
      }>(`/state/market/timeseries?venue=${venue}&symbol=${symbol}&metric=${metric}&window=${window}`),
    refetchInterval: REFETCH_INTERVAL,
    retry: 2,
    enabled: !!venue && !!symbol && !!metric,
  })
}

export function useMarketAlerts(limit: number = 50) {
  return useQuery({
    queryKey: ['market', 'alerts', limit],
    queryFn: () => apiGet<MarketAlert[]>('/state/market/alerts?limit=' + limit),
    refetchInterval: REFETCH_INTERVAL,
    retry: 2,
  })
}

export function useMarketStatus() {
  return useQuery({
    queryKey: ['market', 'status'],
    queryFn: () => apiGet<MarketDataStatus>('/state/market/status'),
    refetchInterval: 10000, // Less frequent
    retry: 2,
  })
}
