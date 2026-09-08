import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { DepthResponse, MarketContextResponse } from '../types'

/**
 * Poll cadence per interval, matching useCandles: the context panes sit
 * underneath the price chart and there is no reason for them to refresh on a
 * different clock than the bars they are aligned to.
 */
const REFETCH_MS: Record<string, number> = {
  '1m': 15_000,
  '5m': 30_000,
  '15m': 60_000,
  '1h': 120_000,
  '4h': 300_000,
  '1d': 600_000,
}

/** Funding and open interest, bucketed to the chart's candle boundaries. */
export function useMarketContext(symbol: string, interval: string, limit = 300) {
  return useQuery({
    queryKey: ['market-context', symbol, interval, limit],
    queryFn: () =>
      apiGet<MarketContextResponse>(
        `/state/market/context?venue=hyperliquid&symbol=${encodeURIComponent(symbol)}` +
          `&interval=${encodeURIComponent(interval)}&limit=${limit}`,
      ),
    refetchInterval: REFETCH_MS[interval] ?? 60_000,
    retry: 1,
  })
}

/**
 * The current order book.
 *
 * Deliberately on its own short clock rather than the chart's: the book is a
 * photograph of resting intent and a four-hour-old one describes nothing. It is
 * also never cached across symbols, so switching symbol cannot briefly show the
 * previous market's ladder.
 */
export function useDepth(symbol: string, enabled = true) {
  return useQuery({
    queryKey: ['market-depth', symbol],
    queryFn: () =>
      apiGet<DepthResponse>(
        `/state/market/depth?venue=hyperliquid&symbol=${encodeURIComponent(symbol)}`,
      ),
    refetchInterval: 10_000,
    retry: 1,
    enabled,
  })
}
