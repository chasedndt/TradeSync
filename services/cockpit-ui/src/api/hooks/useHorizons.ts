import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../client'
import type { HorizonChartPayload, HorizonKey, HorizonPage, HorizonReading } from '../horizonTypes'

/** The timeframe page for one market. Measured once an hour server-side; polled quickly while Hermes is reading. */
export function useHorizonPage(symbol: string) {
  return useQuery({
    queryKey: ['horizons', symbol],
    queryFn: () => apiGet<HorizonPage>(`/state/market/horizons?symbol=${encodeURIComponent(symbol)}`),
    refetchInterval: (query) => (query.state.data?.reading.status === 'running' ? 4_000 : 300_000),
    placeholderData: keepPreviousData,
    retry: 1,
  })
}

/** Candles, every feature's overlay and the record's cone for one horizon. */
export function useHorizonChart(symbol: string, horizon: HorizonKey) {
  return useQuery({
    queryKey: ['horizon-chart', symbol, horizon],
    queryFn: () => apiGet<HorizonChartPayload>(`/state/market/horizons/chart?symbol=${encodeURIComponent(symbol)}&horizon=${horizon}`),
    staleTime: 600_000,
    retry: 1,
  })
}

/** Ask Hermes for a prose reading of the page; the page polls until it is done. */
export function useStartHorizonReading(symbol: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiPost<{ status: string; reading: HorizonReading }>(`/state/market/horizons/reading?symbol=${encodeURIComponent(symbol)}`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['horizons', symbol] }),
  })
}
