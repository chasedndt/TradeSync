/** A price at a precision that suits its size: 79,123.4, 151.27, 0.2143, 0.001235. */
export function formatChartPrice(value: number): string {
  const size = Math.abs(value)
  const digits = size >= 1000 ? 1 : size >= 1 ? 2 : size >= 0.01 ? 4 : 6
  return value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

/** A span of time in its two largest units: 2d 4h, 3h 15m, 45m, 30s. */
export function formatDuration(seconds: number): string {
  const sign = seconds < 0 ? '-' : ''
  let rest = Math.abs(Math.round(seconds))
  const days = Math.floor(rest / 86_400)
  rest -= days * 86_400
  const hours = Math.floor(rest / 3_600)
  rest -= hours * 3_600
  const minutes = Math.floor(rest / 60)
  const secs = rest - minutes * 60

  const parts = days
    ? [`${days}d`, hours ? `${hours}h` : '']
    : hours
      ? [`${hours}h`, minutes ? `${minutes}m` : '']
      : minutes
        ? [`${minutes}m`]
        : [`${secs}s`]
  return sign + parts.filter(Boolean).join(' ')
}
