import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { CandleResponse } from '../types'

/** Poll cadence per interval: no point refetching a 4h candle every 5 seconds. */
const REFETCH_MS: Record<string, number> = {
  '1m': 15_000,
  '5m': 30_000,
  '15m': 60_000,
  '1h': 120_000,
  '4h': 300_000,
  '1d': 600_000,
}

export function useCandles(symbol: string, interval: string, limit = 300) {
  return useQuery({
    queryKey: ['candles', symbol, interval, limit],
    queryFn: () =>
      apiGet<CandleResponse>(
        `/state/market/candles?venue=hyperliquid&symbol=${encodeURIComponent(symbol)}` +
          `&interval=${encodeURIComponent(interval)}&limit=${limit}`,
      ),
    refetchInterval: REFETCH_MS[interval] ?? 60_000,
    retry: 1,
  })
}
