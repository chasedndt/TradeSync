import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../client'
import type { BandKey, BandReading, HorizonChartPayload, HorizonKey, HorizonPage } from '../horizonTypes'

const busy = (page: HorizonPage | undefined): boolean =>
  Boolean(page && (Object.values(page.readings).some((r) => r.status === 'running') || Object.values(page.errors).includes('measuring')))

/**
 * The timeframe page for one market. Short-term horizons are re-measured every
 * five minutes server-side and daily ones hourly; polled quickly while a
 * measurement or a Hermes reading is still running.
 */
export function useHorizonPage(symbol: string) {
  return useQuery({
    queryKey: ['horizons', symbol],
    queryFn: () => apiGet<HorizonPage>(`/state/market/horizons?symbol=${encodeURIComponent(symbol)}`),
    refetchInterval: (query) => (busy(query.state.data) ? 5_000 : 60_000),
    placeholderData: keepPreviousData,
    retry: 1,
  })
}

/** Candles, every feature's overlay and the record's cone for one horizon; refetched when its measurement changes. */
export function useHorizonChart(symbol: string, horizon: HorizonKey, measuredAt: string | undefined) {
  return useQuery({
    queryKey: ['horizon-chart', symbol, horizon, measuredAt ?? 'pending'],
    queryFn: () => apiGet<HorizonChartPayload>(`/state/market/horizons/chart?symbol=${encodeURIComponent(symbol)}&horizon=${horizon}`),
    enabled: Boolean(measuredAt),
    placeholderData: keepPreviousData,
    staleTime: 300_000,
    retry: 1,
  })
}

/** Measure the market again now, both short-term and daily. */
export function useRefreshHorizons(symbol: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiPost<{ symbol: string; computed_at: Record<string, string>; errors: Record<string, string> }>(
      `/state/market/horizons/refresh?symbol=${encodeURIComponent(symbol)}`, {}),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['horizons', symbol] })
      qc.invalidateQueries({ queryKey: ['horizon-chart', symbol] })
    },
  })
}

/** Ask Hermes for a reading of one band; the page polls until it finishes. */
export function useStartHorizonReading(symbol: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (band: BandKey) => apiPost<{ status: string; reading: BandReading }>(
      `/state/market/horizons/reading?symbol=${encodeURIComponent(symbol)}&scope=${band}`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['horizons', symbol] }),
  })
}
