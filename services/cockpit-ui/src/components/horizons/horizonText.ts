import type { RecordLean, RecordStats } from '../../api/horizonTypes'

export const LEAN_LABEL: Record<RecordLean, string> = {
  up: 'record leans higher',
  down: 'record leans lower',
  mixed: 'no consistent direction',
  too_few: 'too thin to judge',
  unavailable: 'not measurable yet',
}

export const TREND_WORDS: Record<string, string> = {
  above_rising: 'above a rising',
  above_falling: 'above a falling',
  below_rising: 'below a rising',
  below_falling: 'below a falling',
}

/** +2.1%, −0.4%. */
export const signedPct = (v: number | null | undefined, digits = 1): string =>
  v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(digits)}%`

/** "3 days" → "3-day", "2 weeks" → "2-week": a horizon label as it reads before a noun. */
export const horizonAdjective = (label: string): string => label.replace(/^(\d+) (\w+?)s?$/, '$1-$2')

export function recordLine(stats: RecordStats | undefined, horizonLabel: string): string {
  if (!stats || !stats.days) return 'No comparable days in the record.'
  const share = Math.round((stats.share_up ?? 0) * 100)
  return `${stats.days.toLocaleString()} comparable days (${stats.independent_windows} non-overlapping ${horizonAdjective(horizonLabel)} windows): ` +
    `higher ${share}% of the time, median ${signedPct(stats.median_pct)}, middle half ${signedPct(stats.p25_pct)} to ${signedPct(stats.p75_pct)}.`
}
