import type { LabDirection } from '../../api/strikezoneTypes'

/** Signed dollars: +$4.35, −$159.41. */
export const usd = (v: number | null | undefined, digits = 2): string =>
  v == null ? '—' : `${v < 0 ? '−' : v > 0 ? '+' : ''}$${Math.abs(v).toFixed(digits)}`

/** A price at a precision that suits its size. */
export const price = (v: number | null | undefined): string =>
  v == null ? '—' : v >= 1000 ? v.toLocaleString(undefined, { maximumFractionDigits: 1 }) : v >= 1 ? v.toFixed(2) : v.toPrecision(4)

export const pct = (v: number | null | undefined, digits = 0): string => (v == null ? '—' : `${v.toFixed(digits)}%`)

/** A 0 to 1 share as a whole percentage. */
export const share = (v: number | null | undefined): string => (v == null ? '—' : `${Math.round(v * 100)}%`)

export const minutesAgo = (m: number | null | undefined): string => {
  if (m == null) return 'never'
  if (m < 1) return 'just now'
  if (m < 60) return `${Math.round(m)}m ago`
  if (m < 1440) return `${(m / 60).toFixed(m < 600 ? 1 : 0)}h ago`
  return `${Math.round(m / 1440)}d ago`
}

export const since = (iso: string | null | undefined): string =>
  iso ? minutesAgo((Date.now() - new Date(iso).getTime()) / 60_000) : 'never'

/** "09-13 07:00" in UTC. */
export const utcTime = (iso: string | null | undefined): string => (iso ? new Date(iso).toISOString().slice(5, 16).replace('T', ' ') : '—')

export const toneOf = (v: number | null | undefined): string => (v == null || v === 0 ? 'tone-dim' : v > 0 ? 'tone-good' : 'tone-bad')

export const directionLabel = (d: LabDirection | null | undefined): string =>
  d === 'long' ? 'LONG' : d === 'short' ? 'SHORT' : 'NO TRADE'

export const humanize = (s: string | null | undefined): string => (s ? s.split('_').join(' ') : '—')
