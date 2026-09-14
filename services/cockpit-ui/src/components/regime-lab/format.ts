import type { CoverageReason, ReplayHorizon, ReplayHours } from '../../api/regimeLabTypes'

/** Rulebook block names as the page shows them. */
export const BLOCK_LABELS: Record<string, string> = {
  price_volatility: 'Price & volatility',
  liquidity: 'Liquidity',
  positioning: 'Positioning',
  spot_premium: 'Spot premium',
  macro_flows: 'Macro flows',
}

export const blockLabel = (block: string): string => BLOCK_LABELS[block] ?? block.split('_').join(' ')

/** Coverage reasons in the order they are listed, from usable to missing. */
export const REASON_ORDER: CoverageReason[] = ['usable', 'stale', 'flat', 'collecting_history', 'display_only', 'unavailable']

export const REASON_LABELS: Record<CoverageReason, string> = {
  usable: 'usable',
  stale: 'stale',
  flat: 'flat values',
  collecting_history: 'collecting history',
  display_only: 'display only',
  unavailable: 'unavailable',
}

/** What each reason means. "Fresh" always means a reading within its feature's stale limit. */
export const REASON_HINTS: Record<CoverageReason, string> = {
  usable: 'A fresh reading with a z-score',
  stale: 'A reading past its stale limit',
  flat: 'A fresh reading whose recent values are all identical, so it has no dispersion',
  collecting_history: 'Fewer prior readings than the catalog minimum',
  display_only: 'Shown for context; never normalized or scored',
  unavailable: 'No current reading, or one the normalizer refused',
}

export const WINDOW_LABELS: Record<ReplayHours, string> = { 24: 'Last 24 hours', 168: 'Last 7 days', 720: 'Last 30 days' }
export const HORIZON_LABELS: Record<ReplayHorizon, string> = { 15: '15 minutes', 60: '60 minutes', 240: '4 hours' }

/** A reading at a precision that suits its size; tiny rates in exponent form. */
export function reading(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const size = Math.abs(value)
  if (size >= 1e9) return `${(value / 1e9).toFixed(2)}b`
  if (size >= 1e6) return `${(value / 1e6).toFixed(2)}m`
  if (size >= 100) return value.toLocaleString('en-GB', { maximumFractionDigits: 1 })
  if (size !== 0 && size < 0.001) return value.toExponential(2)
  return String(Number(value.toFixed(4)))
}

/** One decimal below ten unless it would read ".0"; whole numbers otherwise. */
function short(n: number): string {
  const tenths = Number(n.toFixed(1))
  return n < 10 && !Number.isInteger(tenths) ? tenths.toFixed(1) : String(Math.round(n))
}

/** Milliseconds as seconds, minutes, hours or days. */
export function duration(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return '—'
  const seconds = ms / 1000
  if (seconds < 60) return `${short(seconds)} s`
  const minutes = seconds / 60
  if (minutes < 60) return `${short(minutes)} min`
  const hours = minutes / 60
  if (hours < 48) return `${short(hours)} h`
  return `${Math.round(hours / 24)} d`
}

/** A signed number with a true minus sign. */
export function signed(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${Math.abs(value).toFixed(digits)}`
}

/** A 0 to 1 share as a percentage. */
export const percent = (share: number | null | undefined, digits = 1): string =>
  share == null || !Number.isFinite(share) ? '—' : `${(share * 100).toFixed(digits)}%`

/** A difference between shares, in percentage points. */
export const points = (delta: number | null | undefined): string =>
  delta == null || !Number.isFinite(delta) ? '—' : `${signed(delta * 100, 1)} pts`

export const count = (n: number | null | undefined): string => (n == null ? '—' : n.toLocaleString('en-GB'))
