/** The value at or immediately before `time` in points sorted by time; undefined before the first point. */
export function valueAt(points: [number, number][], time: number): number | undefined {
  let lo = 0
  let hi = points.length - 1
  let found: number | undefined
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (points[mid][0] <= time) {
      found = points[mid][1]
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  return found
}
