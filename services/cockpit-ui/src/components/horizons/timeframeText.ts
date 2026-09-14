import type { CombinedLean, HeldOut, Interval, RecordLean, RecordStats } from '../../api/horizonTypes'

export const LEAN_LABEL: Record<RecordLean, string> = {
  up: 'record leans higher',
  down: 'record leans lower',
  mixed: 'no consistent direction',
  too_few: 'too thin to judge',
  unavailable: 'not measurable yet',
}

export const COMBINED_LABEL: Record<CombinedLean, string> = {
  up: 'weighted higher',
  down: 'weighted lower',
  balanced: 'weighted balanced',
  unweighted: 'no earned weight',
}

export const AGREEMENT: Record<string, string> = {
  up: 'records lean higher',
  down: 'records lean lower',
  mixed: 'no consistent direction',
  split: 'horizons disagree',
  unjudged: 'too thin to judge',
}

export const TREND_WORDS: Record<string, string> = {
  above_rising: 'above a rising',
  above_falling: 'above a falling',
  below_rising: 'below a rising',
  below_falling: 'below a falling',
}

export const INTERVAL_WORDS: Record<Interval, string> = { '15m': '15-minute', '1h': 'hourly', '1d': 'daily' }

/** +2.1%, −0.4%. */
export const signedPct = (v: number | null | undefined, digits = 1): string =>
  v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(digits)}%`

/** 0.62 → 62%. */
export const pct = (v: number | null | undefined): string => (v == null ? '—' : `${Math.round(v * 100)}%`)

/** "4 hours" → "4-hour": a horizon label as it reads before a noun. */
export const adjective = (label: string): string => label.replace(/^(\d+) (\w+?)s?$/, '$1-$2')

export const capitalise = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1)

/** "14 Sep, 12:41": an absolute local time a reader can check against the clock. */
export const clock = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'

export function recordLine(stats: RecordStats | undefined, horizonLabel: string): string {
  if (!stats || !stats.days) return 'No comparable bars in the record.'
  return `${stats.days.toLocaleString()} comparable bars (${stats.independent_windows} non-overlapping ${adjective(horizonLabel)} windows): ` +
    `higher ${pct(stats.share_up)} of the time, median ${signedPct(stats.median_pct, 2)}, middle half ${signedPct(stats.p25_pct, 2)} to ${signedPct(stats.p75_pct, 2)}.`
}

export function heldOutLine(h: HeldOut): string {
  switch (h.status) {
    case 'measured':
      return `${pct(h.hit_rate)} right vs ${pct(h.chance)} by chance, ${h.test_windows} test windows`
    case 'too_few_test_windows':
      return `only ${h.test_windows} test windows`
    case 'no_leaning_state':
      return 'no state leaned in the older history'
    default:
      return 'too little history'
  }
}
