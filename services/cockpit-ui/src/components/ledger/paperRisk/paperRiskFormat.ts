import type { LimitValues } from '../../../api/paperRiskTypes'

/** Pure formatting for the Paper risk panel; no React, so the node tests can import it. */

export type Tone = 'good' | 'warn' | 'bad' | 'dim'

const missing = (value: number | null | undefined): value is null | undefined => value == null || !Number.isFinite(value)

export function usd(value: number | null | undefined): string {
  return missing(value) ? '—' : `${value.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDC`
}

export function signedUsd(value: number | null | undefined): string {
  if (missing(value)) return '—'
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}${usd(Math.abs(value))}`
}

export function percent(fraction: number | null | undefined, digits = 2): string {
  return missing(fraction) ? '—' : `${(fraction * 100).toFixed(digits)}%`
}

/** Under three quarters of a limit is comfortable, up to the limit is a warning, at or past it is a breach. */
export function meterTone(fractionOfLimit: number | null | undefined): Tone {
  if (missing(fractionOfLimit)) return 'dim'
  return fractionOfLimit >= 1 ? 'bad' : fractionOfLimit >= 0.75 ? 'warn' : 'good'
}

export function meterWidth(fractionOfLimit: number | null | undefined): string {
  return missing(fractionOfLimit) ? '0%' : `${Math.round(Math.min(1, Math.max(0, fractionOfLimit)) * 100)}%`
}

export function utcStamp(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—'
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : `${date.toISOString().slice(0, 19).replace('T', ' ')} UTC`
}

export function ageText(seconds: number | null | undefined): string {
  if (missing(seconds)) return '—'
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

export function codeLabel(code: string): string {
  const words = code.toLowerCase().split('_')
  return words.map((word, index) => (index === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word)).join(' ')
}

export type LimitField = { key: keyof LimitValues; label: string; unit: 'usdc' | 'percent' | 'count' | 'seconds' | 'ratio'; min: number; max: number }

/** Bounds mirror the state-api request model; the database constraints are the backstop. */
export const LIMIT_FIELDS: LimitField[] = [
  { key: 'daily_loss_limit_usdc', label: 'Daily loss limit', unit: 'usdc', min: 0.01, max: 1_000_000 },
  { key: 'max_drawdown_fraction', label: 'Maximum drawdown from peak', unit: 'percent', min: 0.01, max: 99.99 },
  { key: 'max_gross_exposure_fraction', label: 'Gross exposure of equity', unit: 'percent', min: 0.01, max: 1000 },
  { key: 'max_symbol_exposure_fraction', label: 'Per-symbol exposure of equity', unit: 'percent', min: 0.01, max: 1000 },
  { key: 'max_bucket_exposure_fraction', label: 'Correlated bucket exposure of equity', unit: 'percent', min: 0.01, max: 1000 },
  { key: 'correlation_threshold', label: 'Correlation that joins a bucket', unit: 'ratio', min: 0.01, max: 1 },
  { key: 'max_concurrent_positions', label: 'Open positions', unit: 'count', min: 1, max: 50 },
  { key: 'max_entry_quote_age_s', label: 'Entry quote age', unit: 'seconds', min: 1, max: 30 },
  { key: 'max_mark_age_s', label: 'Open position mark age', unit: 'seconds', min: 1, max: 600 },
]

export function limitText(field: LimitField, value: number): string {
  if (field.unit === 'usdc') return usd(value)
  if (field.unit === 'percent') return percent(value)
  if (field.unit === 'seconds') return `${value}s`
  return String(value)
}

/** The value typed in a limit input as the API expects it; null when it is not a number inside the bounds. */
export function parseLimit(field: LimitField, text: string): number | null {
  if (!text.trim()) return null
  const typed = Number(text)
  if (!Number.isFinite(typed) || typed < field.min || typed > field.max) return null
  if (field.unit === 'count' && !Number.isInteger(typed)) return null
  return field.unit === 'percent' ? typed / 100 : typed
}

export function inputValue(field: LimitField, value: number): string {
  return field.unit === 'percent' ? String(Number((value * 100).toFixed(4))) : String(value)
}
