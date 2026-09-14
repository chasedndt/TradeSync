/** Retracement levels drawn by the fib tool. */
export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1] as const

export interface FibLevel {
  level: number
  price: number
}

/**
 * The price at each level for a move from `start` to `end`.
 *
 * As on TradingView, level 1 sits at the first anchor (where the move began)
 * and level 0 at the second (where it ended), so 0.618 is how far price has
 * given back of that move.
 */
export function fibLevels(startPrice: number, endPrice: number): FibLevel[] {
  return FIB_LEVELS.map((level) => ({ level, price: endPrice + (startPrice - endPrice) * level }))
}
