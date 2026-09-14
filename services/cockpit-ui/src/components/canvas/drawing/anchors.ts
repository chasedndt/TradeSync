/**
 * Time on the chart, as its bars define it.
 *
 * Lightweight Charts positions everything by logical bar index and has no
 * coordinate for a time it holds no bar for, which is why a shape anchored past
 * the last candle could not be drawn before. Anchors are stored as time, so a
 * drawing is the same on every interval; these functions convert between time
 * and logical index using the bars the chart holds, and continue past either
 * end at the interval's length.
 */

export interface TimeAxis {
  /** Bar open times, ascending, in UNIX seconds. */
  times: readonly number[]
  /** Seconds per bar, used beyond either end of the data. */
  step: number
}

/** Fractional logical index for a time, or null when there are no bars to measure against. */
export function timeToLogical(time: number, axis: TimeAxis): number | null {
  const { times, step } = axis
  const count = times.length
  if (count === 0 || !(step > 0) || !Number.isFinite(time)) return null
  const first = times[0]
  const last = times[count - 1]
  if (time <= first) return (time - first) / step
  if (time >= last) return count - 1 + (time - last) / step

  // The bar at or before `time`, then the fraction of the way to the next one.
  let low = 0
  let high = count - 1
  while (high - low > 1) {
    const middle = (low + high) >> 1
    if (times[middle] <= time) low = middle
    else high = middle
  }
  const span = times[high] - times[low]
  return low + (span > 0 ? (time - times[low]) / span : 0)
}

/** Time for a fractional logical index, or null when there are no bars to measure against. */
export function logicalToTime(logical: number, axis: TimeAxis): number | null {
  const { times, step } = axis
  const count = times.length
  if (count === 0 || !(step > 0) || !Number.isFinite(logical)) return null
  if (logical <= 0) return times[0] + logical * step
  if (logical >= count - 1) return times[count - 1] + (logical - (count - 1)) * step
  const low = Math.floor(logical)
  return times[low] + (logical - low) * (times[low + 1] - times[low])
}
