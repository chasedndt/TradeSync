import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPut } from '../client'
import type { BandKey } from '../horizonTypes'
import type { BandSchedule, ScheduleValue } from '../readingScheduleTypes'
import type { ReadingSchedule } from '../readingScheduleTypes'

/** The market's Hermes reading schedule per band: off unless an operator set one. */
export function useReadingSchedule(symbol: string) {
  return useQuery({
    queryKey: ['reading-schedule', symbol],
    queryFn: () => apiGet<ReadingSchedule>(`/state/market/horizons/reading-schedule?symbol=${encodeURIComponent(symbol)}`),
    refetchInterval: 60_000,
    retry: 1,
  })
}

/** Set one band's schedule; the state API keeps an audit row with the value it replaced. */
export function useSaveReadingSchedule(symbol: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (change: { scope: BandKey; enabled: boolean; daily_time: string }) =>
      apiPut<{ schedule: BandSchedule; previous: ScheduleValue | null; changed_by: string; changed_at: string }>(
        '/state/market/horizons/reading-schedule', { symbol, changed_by: 'operator', ...change }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reading-schedule', symbol] })
      qc.invalidateQueries({ queryKey: ['horizons', symbol] })
    },
  })
}
