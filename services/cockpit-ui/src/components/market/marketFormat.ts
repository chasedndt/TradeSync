/** $1.2m, $840k, $95. */
export const usdCompact = (v: number | null | undefined): string => {
  if (v == null || !Number.isFinite(v)) return '—'
  const abs = Math.abs(v)
  const sign = v < 0 ? '−' : ''
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}b`
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}m`
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}k`
  return `${sign}$${abs.toFixed(0)}`
}

/** "14 Sep, 18:20": an absolute local time. */
export const when = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'
