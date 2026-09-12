import { useMemo } from 'react'
import { useMarketSnapshots } from './useMarketData'

/**
 * The symbols this deployment actually tracks, taken from the market-data
 * service rather than a constant in each page.
 *
 * Four pages used to carry their own copy of "BTC, ETH, SOL". Adding a pair
 * meant finding all four, and the one that was missed showed a stale list
 * while the API served more. The service is configured once (MARKET_SYMBOLS
 * in compose) and everything else reads what it reports.
 *
 * Order is the service's configured order, so the list is stable across
 * refreshes rather than reshuffling by whichever symbol updated last.
 */
export const FALLBACK_SYMBOLS = ['BTC-PERP', 'ETH-PERP', 'SOL-PERP']

export function useTrackedSymbols(): { symbols: string[]; isLoading: boolean; isFallback: boolean } {
  const { data, isLoading } = useMarketSnapshots()
  return useMemo(() => {
    const seen = new Set<string>()
    const symbols: string[] = []
    for (const snapshot of data?.snapshots ?? []) {
      if (snapshot.venue === 'hyperliquid' && !seen.has(snapshot.symbol)) {
        seen.add(snapshot.symbol)
        symbols.push(snapshot.symbol)
      }
    }
    if (symbols.length === 0) {
      return { symbols: FALLBACK_SYMBOLS, isLoading, isFallback: true }
    }
    return { symbols, isLoading, isFallback: false }
  }, [data, isLoading])
}
