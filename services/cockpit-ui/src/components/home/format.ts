export function formatUsd(value?: number | null, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: value > 10_000 ? 1 : digits }).format(value)
}

export function formatCompactUsd(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 2 }).format(value)
}

export function formatPercent(value?: number | null, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`
}

export function formatAge(seconds?: number | null) {
  if (seconds == null || !Number.isFinite(seconds)) return '—'
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

export function formatPrice(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return '—'
  const digits = value < 1 ? 4 : value < 1000 ? 2 : 1
  return value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function formatWhen(minutes: number) {
  if (minutes < 0) return 'under way'
  if (minutes < 60) return `in ${minutes}m`
  if (minutes < 48 * 60) return `in ${Math.floor(minutes / 60)}h ${minutes % 60}m`
  return `in ${Math.floor(minutes / 1440)}d`
}
