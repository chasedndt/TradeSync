import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { HeatmapWindow, LiquidationMap, LiquidityHeatmap, MapWindow, ReceivedLiquidations, ReceivedWindow, WindowCandle } from '../liquidityTypes'

const q = (symbol: string) => encodeURIComponent(symbol)

/** Resting liquidity per time bucket and price level, from books recorded once a minute. */
export function useLiquidityHeatmap(symbol: string, window: HeatmapWindow) {
  return useQuery({
    queryKey: ['liquidity-heatmap', symbol, window],
    queryFn: () => apiGet<LiquidityHeatmap>(`/state/market/liquidity-heatmap?symbol=${q(symbol)}&window=${window}`),
    refetchInterval: 60_000,
    placeholderData: keepPreviousData,
    retry: 1,
  })
}

/** Estimated liquidation levels from open-interest changes; the state API caches each window for five minutes. */
export function useLiquidationMap(symbol: string, window: MapWindow) {
  return useQuery({
    queryKey: ['liquidation-map', symbol, window],
    queryFn: () => apiGet<LiquidationMap>(`/state/market/liquidation-map?symbol=${q(symbol)}&window=${window}`),
    refetchInterval: 300_000,
    placeholderData: keepPreviousData,
    retry: 1,
  })
}

/** Liquidations received from Bybit and Binance, by side over time. */
export function useReceivedLiquidations(symbol: string, window: ReceivedWindow) {
  return useQuery({
    queryKey: ['received-liquidations', symbol, window],
    queryFn: () => apiGet<ReceivedLiquidations>(`/state/market/liquidations?symbol=${q(symbol)}&window=${window}`),
    refetchInterval: 30_000,
    placeholderData: keepPreviousData,
    retry: 1,
  })
}

/** The newest candles for a heatmap window, at the interval the window is drawn on. */
export function useWindowCandles(symbol: string, interval: string, limit: number) {
  return useQuery({
    queryKey: ['window-candles', symbol, interval, limit],
    queryFn: async () => (await apiGet<{ candles: WindowCandle[] }>(
      `/state/market/candles?venue=hyperliquid&symbol=${q(symbol)}&interval=${interval}&limit=${limit}`)).candles ?? [],
    refetchInterval: 60_000,
    placeholderData: keepPreviousData,
    retry: 1,
  })
}
