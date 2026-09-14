const STEPS = [1, 2, 2.5, 5, 10]

/** The smallest clean axis bound (1, 2, 2.5 or 5 times a power of ten) at or above ``value``. */
export function niceCeiling(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 0.1
  const base = 10 ** Math.floor(Math.log10(value))
  for (const step of STEPS) {
    if (step * base >= value - 1e-12) return step * base
  }
  return 10 * base
}

/**
 * A column from the baseline to a value: rounded at the data end, square at the
 * baseline. SVG y grows downward, so an end above the baseline has a smaller y.
 */
export function columnPath(x: number, width: number, baseline: number, end: number, radius = 4): string {
  const height = Math.abs(end - baseline)
  const r = Math.min(radius, width / 2, height)
  const right = x + width
  const toward = end <= baseline ? r : -r
  return [
    `M${x},${baseline}`,
    `V${end + toward}`,
    `Q${x},${end} ${x + r},${end}`,
    `H${right - r}`,
    `Q${right},${end} ${right},${end + toward}`,
    `V${baseline}`,
    'Z',
  ].join(' ')
}
