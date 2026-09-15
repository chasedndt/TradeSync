import type {
  CombinationSource,
  CombinationWindow,
  DifferenceVerdict,
  ForecastComparison,
  ForecastName,
  RatioInterval,
  ReliabilityBin,
  ScoreMetric,
} from '../../../api/evidenceCombinationTypes'

/** Pure wording and geometry for the evidence-combination panel; no React, so it can be tested alone. */

const MINUS = '−'
const finite = (value: number | null | undefined): value is number => value != null && Number.isFinite(value)

export const FORECAST_ORDER: ForecastName[] = ['base_rate', 'rulebook_score', 'combined', 'combined_without_dependence_adjustment']

export const FORECAST_LABELS: Record<ForecastName, string> = {
  base_rate: 'Base rate',
  rulebook_score: 'Rulebook score, calibrated',
  combined: 'Combined sources',
  combined_without_dependence_adjustment: 'Combined, counted as independent',
}

export const VERDICT_WORDS: Record<DifferenceVerdict, string> = {
  better: 'better',
  worse: 'worse',
  not_distinguishable: 'not distinguishable',
  not_measurable: 'not measurable yet',
}

export const STANDING_LABELS: Record<CombinationSource['standing'], string> = {
  scoring: 'scoring',
  context_only: 'context only',
  not_in_catalog: 'not in catalog',
}

/**
 * A source's lean is named only when one of its intervals excludes ×1.00. Below
 * that, the sign of a point estimate such as ×0.99 is noise, and naming it
 * would invite reading a direction into a coin.
 */
export function leanLabel(source: Pick<CombinationSource, 'fit_calls' | 'interval_excludes_one' | 'polarity'>): string {
  if (source.fit_calls === 0) return 'no record yet'
  if (!source.interval_excludes_one || source.polarity === 'none') return 'no measurable lean'
  return source.polarity === 'follows' ? 'leans with the move' : 'leans contrarian'
}

/** Lower loss is better, so "better" earns the good tone and "worse" the bad one. */
export const verdictTone = (verdict: DifferenceVerdict): string =>
  verdict === 'better' ? 'tone-good' : verdict === 'worse' ? 'tone-bad' : 'tone-dim'

/** A 0 to 1 probability as a percentage: 50.2%. */
export const probabilityPct = (value: number | null | undefined, digits = 1): string =>
  finite(value) ? `${(value * 100).toFixed(digits)}%` : '—'

/** A gap between probabilities in percentage points: 1.3 pts. */
export const points = (value: number | null | undefined): string => (finite(value) ? `${(value * 100).toFixed(1)} pts` : '—')

export const decimal = (value: number | null | undefined, digits = 4): string => (finite(value) ? value.toFixed(digits) : '—')

/** A score difference with its sign and a true minus: +0.0016, −0.0040. Zero at this precision is unsigned. */
export function signedDecimal(value: number | null | undefined, digits = 4): string {
  if (!finite(value)) return '—'
  const text = Math.abs(value).toFixed(digits)
  if (Number(text) === 0) return text
  return `${value > 0 ? '+' : MINUS}${text}`
}

export const differenceRange = (low: number | null | undefined, high: number | null | undefined, digits = 4): string =>
  finite(low) && finite(high) ? `${signedDecimal(low, digits)} to ${signedDecimal(high, digits)}` : 'interval not measurable yet'

/** A likelihood ratio as a multiplier on the odds: ×1.08. */
export const ratioText = (value: number | null | undefined, digits = 2): string => (finite(value) ? `×${value.toFixed(digits)}` : '—')

export const ratioRange = (interval: RatioInterval): string => `${interval.low.toFixed(2)} to ${interval.high.toFixed(2)}`

export function comparisonFor(
  comparisons: ForecastComparison[],
  candidate: ForecastName,
  baseline: ForecastName,
  metric: ScoreMetric,
): ForecastComparison | undefined {
  return comparisons.find((c) => c.candidate === candidate && c.baseline === baseline && c.metric === metric)
}

/** The regimes a source's ratio was conditioned on, or that it was pooled everywhere. */
export function conditionedRegimes(source: CombinationSource): string {
  const names = source.regimes.filter((regime) => regime.conditioned).map((regime) => regime.regime)
  return names.length ? names.join(', ') : 'none, pooled'
}

/** Sources with a fitting record first, most effective windows first; then the rest by name. */
export function sortSources(sources: CombinationSource[]): CombinationSource[] {
  return [...sources].sort(
    (a, b) =>
      Number(b.fit_calls > 0) - Number(a.fit_calls > 0) ||
      b.fit_effective_windows - a.fit_effective_windows ||
      a.label.localeCompare(b.label),
  )
}

export function windowSummary(window: CombinationWindow): string {
  const decisions = window.decisions.toLocaleString('en-GB')
  const independent = window.independent_windows.pooled.toLocaleString('en-GB')
  return `${decisions} decisions (${window.effective_windows.toFixed(1)} effective windows, ${independent} independent)`
}

export interface PlotFrame {
  left: number
  top: number
  size: number
}

export interface PlottedBin {
  cx: number
  cy: number
  low: number | null
  high: number | null
}

/** A reliability bin inside the square plot: forecast across, share that rose upward (1 at the top). */
export function plotPoint(bin: Pick<ReliabilityBin, 'mean_probability' | 'rise_share' | 'low' | 'high'>, frame: PlotFrame): PlottedBin {
  const y = (value: number) => frame.top + (1 - value) * frame.size
  return {
    cx: frame.left + bin.mean_probability * frame.size,
    cy: y(bin.rise_share),
    low: finite(bin.low) ? y(bin.low) : null,
    high: finite(bin.high) ? y(bin.high) : null,
  }
}

/** The square's side for the width available: never cramped, never larger than a glance needs. */
export const chartSize = (available: number): number => Math.max(140, Math.min(280, Math.floor(available)))
