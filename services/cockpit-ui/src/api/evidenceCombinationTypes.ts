import type { ComputingReading, MeasuredReading } from './outcomeEvidenceTypes'

/** Shapes of GET /state/research/evidence-combination (evidence_combination_v1). Research reading only. */

export type ForecastName = 'base_rate' | 'rulebook_score' | 'combined' | 'combined_without_dependence_adjustment'
export type DifferenceVerdict = 'better' | 'worse' | 'not_distinguishable' | 'not_measurable'
export type ScoreMetric = 'brier' | 'log_loss'

export interface RatioInterval {
  estimate: number
  low: number
  high: number
}

export interface CombinationRegime {
  regime: string
  calls: number
  effective_windows: number
  conditioned: boolean
  up_call: RatioInterval
  down_call: RatioInterval
}

export interface CombinationSource {
  source_id: string
  label: string
  standing: 'scoring' | 'context_only' | 'not_in_catalog'
  block: string | null
  fit_calls: number
  fit_effective_windows: number
  up_call_share: number | null
  likelihood_ratio: {
    up_call: RatioInterval
    down_call: RatioInterval
    p_up_call_when_rose: number
    p_up_call_when_fell: number
    effective_windows: number
  }
  unshrunk: { up_call: number | null; down_call: number | null }
  polarity: 'follows' | 'contrarian' | 'none'
  interval_excludes_one: boolean
  regimes: CombinationRegime[]
  test_calls: number
  test_mean_weight: number | null
}

export interface ReliabilityBin {
  decisions: number
  effective_windows: number
  mean_probability: number
  rise_share: number
  low: number | null
  high: number | null
}

export interface ForecastScore {
  decisions: number
  brier: number
  log_loss: number
  mean_probability: number
  rise_share: number
  reliability: number
  resolution: number
  uncertainty: number
  calibration_error: number
  bins_within_interval: number
  miscalibration_detectable: boolean
  bins: ReliabilityBin[]
  calibration?: {
    intercept: number
    slope: number
    decisions: number
    effective_windows: number
    slope_prior_precision: number
  } | null
  test_decisions_without_score?: number
}

export interface ForecastComparison {
  candidate: ForecastName
  baseline: ForecastName
  metric: ScoreMetric
  mean_difference: number
  low: number | null
  high: number | null
  effective_windows: number
  verdict: DifferenceVerdict
}

export interface CombinationWindow {
  decisions: number
  first_opened_at_s: number | null
  last_opened_at_s: number | null
  effective_windows: number
  independent_windows: { per_symbol: number; pooled: number }
  rise_share: number | null
}

export interface PairDependence {
  first: string
  second: string
  shared_decisions: number
  shared_effective_windows: number
  residual_correlation: number | null
  polarity: number
  shrunk_correlation: number
  redundancy: number
}

export interface CombinationEconomics {
  cost_pct: number
  mean_rise_pct: number | null
  mean_fall_pct: number | null
  long_above: number | null
  short_below: number | null
  assumption: string
  base_rate_clears: 'long' | 'short' | null
  test: {
    decisions: number
    long_calls: number
    short_calls: number
    mean_net_return_pct: number | null
    low: number | null
    high: number | null
    effective_windows: number
  }
}

export interface EvidenceCombinationResponse {
  schema_version: string
  method: { version: string; digest: string; prior_windows: number; min_regime_effective: number; holdout_fraction: number }
  horizon_minutes: number
  cost_pct: number
  days: number
  decisions: number
  assessment: 'measured' | 'insufficient_decisions'
  split: {
    holdout_fraction: number
    purged: number
    flat_excluded: number
    fit: CombinationWindow
    test: CombinationWindow
  }
  base_rate: { rise_share: number; log_odds: number; decisions: number; effective_windows: number } | null
  sources: CombinationSource[]
  dependence: {
    rule: string
    prior_windows: number
    pairs: PairDependence[]
    test_mean_weight: number | null
    test_mean_abs_evidence: { adjusted: number | null; counted_as_independent: number | null }
  } | null
  forecasts: Record<ForecastName, ForecastScore> | null
  comparisons: ForecastComparison[]
  economics: CombinationEconomics | null
  reading: string
  authority: 'research_only'
  promotion_allowed: false
  note: string
}

export type EvidenceCombinationReading = (EvidenceCombinationResponse & MeasuredReading) | ComputingReading
