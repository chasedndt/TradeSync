import type { Classification, GroupVerdict } from '../../api/learningTypes'

export const HORIZONS = [15, 60, 240] as const

export const horizonLabel = (minutes: number): string => (minutes % 60 === 0 ? `${minutes / 60}h` : `${minutes}m`)

const finite = (value: number | null | undefined): value is number => value != null && Number.isFinite(value)

/** A value already in percent units, signed: +0.12%, −0.26%. */
export const signedPct = (value: number | null | undefined, digits = 2): string =>
  finite(value) ? `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.abs(value).toFixed(digits)}%` : '—'

/** A 0 to 1 share as a percentage: 35.6%. */
export const sharePct = (value: number | null | undefined, digits = 1): string =>
  finite(value) ? `${(value * 100).toFixed(digits)}%` : '—'

export const shareRange = (low: number | null | undefined, high: number | null | undefined): string =>
  finite(low) && finite(high) ? `${sharePct(low)} to ${sharePct(high)}` : 'interval not measurable yet'

export const pctRange = (low: number | null | undefined, high: number | null | undefined, digits = 2): string =>
  finite(low) && finite(high) ? `${signedPct(low, digits)} to ${signedPct(high, digits)}` : 'interval not measurable yet'

export const netTone = (value: number | null | undefined): string =>
  !finite(value) || value === 0 ? 'tone-dim' : value > 0 ? 'tone-good' : 'tone-bad'

export const CLASSIFICATION_ORDER: Classification[] = [
  'clean_win', 'win_after_drawdown', 'no_follow_through', 'reversed', 'wrong_direction',
]

export const CLASSIFICATION_LABELS: Record<Classification, string> = {
  clean_win: 'Clean win',
  win_after_drawdown: 'Win after drawdown',
  no_follow_through: 'No follow-through',
  reversed: 'Reversed',
  wrong_direction: 'Wrong direction',
}

export const VERDICT_LABELS: Record<GroupVerdict, string> = {
  helping: 'Helping',
  hurting: 'Hurting',
  no_evidence: 'No evidence',
}

export const verdictTone = (verdict: GroupVerdict): string =>
  verdict === 'helping' ? 'tone-good' : verdict === 'hurting' ? 'tone-bad' : 'tone-dim'

export const when = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

export const whenSeconds = (seconds: number | null | undefined): string =>
  finite(seconds) ? when(new Date(seconds * 1000).toISOString()) : '—'

export const shortSymbol = (symbol: string): string => symbol.replace('-PERP', '')

/** The operator's name, remembered per browser for adopt, reject and revert. */
const OPERATOR_KEY = 'tradesync_operator_name'

export function readOperator(): string {
  try {
    return localStorage.getItem(OPERATOR_KEY) ?? ''
  } catch {
    return ''
  }
}

export function saveOperator(name: string): void {
  try {
    localStorage.setItem(OPERATOR_KEY, name)
  } catch {
    // Storage can be unavailable (private windows); the name is simply not remembered.
  }
}
