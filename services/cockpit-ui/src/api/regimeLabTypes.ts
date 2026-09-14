// === Private Regime Lab ===

/** Why a feature does or does not add to coverage; "usable" is a fresh reading with a z-score. */
export type CoverageReason = 'usable' | 'stale' | 'flat' | 'collecting_history' | 'display_only' | 'unavailable'
/** "Fresh" always means a reading within its feature's stale limit. */
export type Freshness = 'fresh' | 'stale' | 'missing'

export interface RegimeLabFeatureResult {
  feature_id: string
  block: string
  unit: string
  provenance: string
  source_authority: string
  decision_role: string
  signal_kind: string
  scoring_eligible: boolean
  availability?: string
  status: string
  current_value: number | null
  score: number | null
  normalized_value?: number | null
  data_quality: number
  scoring_allowed: boolean
  score_mode: string
  reason?: string | null
  history_count?: number
  minimum_history_points: number
  lookback_points: number
  sampling_interval_ms: number
  observed_at_ms?: number
  /** Where the reading comes from, e.g. "Hyperliquid order book". */
  feed: string
  age_ms: number | null
  fresh_after_ms: number
  stale_after_ms: number
  freshness: Freshness
  coverage_reason: CoverageReason
  normalization?: {
    /** The method actually used. */
    method: string
    requested_method?: string
    /** Why the requested method was replaced, when it was. */
    fallback?: string | null
    center: number
    dispersion: number
    mad?: number | null
    z_score: number
    compression: string
  } | null
}

export interface RegimeLabBlockEvidence {
  admitted_feature_ids: string[]
  ready_features: Array<{ feature_id: string; score: number; quality: number }>
  missing_feature_ids: string[]
  score: number | null
  quality: number
  status: string
}

export interface RegimeEvaluation {
  weighted_score: number
  data_coverage: number
  paper_risk_multiplier: number
  missing_blocks: string[]
  contributions: Record<string, {
    weight: number
    score: number
    quality: number
    weighted_quality: number
    raw_contribution: number
  }>
  risk_caps_applied: Array<{ flag: string; cap: number; known: boolean }>
}

export interface RegimeLabFeedHealth {
  feed: string
  features: number
  observed: number
  fresh: number
  stale: number
  newest_age_ms: number | null
  stale_after_ms: number | null
  status: 'fresh' | 'partly_stale' | 'stale' | 'missing'
}

export interface RegimeLabHealth {
  evaluated_at_ms: number
  market_data: { status: string; reason?: string | null; observation_count: number }
  /** Market data answered and at least one reading is fresh. */
  live: boolean
  fresh_features: number
  feature_count: number
  coverage_reasons: Record<CoverageReason, number>
  feeds: RegimeLabFeedHealth[]
}

export interface RegimeLabOverview {
  mode: 'paper_shadow'
  execution_authority: false
  baseline: {
    rulebook_id: string
    version: string
    status: string
    digest: string
    weights: Record<string, number>
    weight_sum: number
    compression_k: number
    activation_mode: string
  }
  catalog: {
    catalog_id: string
    version: string
    digest: string
    feature_count: number
  }
  source_status: {
    status: 'live' | 'unavailable'
    provider: string
    venue: string
    symbol: string
    observation_count: number
    history_source?: string
    reason?: string
  }
  feature_results: RegimeLabFeatureResult[]
  block_evidence: Record<string, RegimeLabBlockEvidence>
  baseline_evaluation: RegimeEvaluation
  health: RegimeLabHealth
}

export type ReplayHours = 24 | 168 | 720
export type ReplayHorizon = 15 | 60 | 240

export interface ReplayRequest {
  hours: ReplayHours
  horizon_minutes: ReplayHorizon
  symbol: string | null
  challenger_weights: Record<string, number>
  challenger_version: string
}

export interface ReplayDecisionCounts {
  replayed: number
  changed: number
  admissions_gained: number
  admissions_lost: number
  direction_flips: number
}

export interface ReplayOutcomeSide {
  admitted_with_outcome: number
  hit_rate: number | null
  /** What this long/short mix would hit by luck, given how the market moved. */
  expected_hit_rate: number | null
  skill: number | null
  mean_signed_return_pct: number | null
}

export interface ReplayOutcomes {
  cases_with_outcome: number
  baseline: ReplayOutcomeSide
  challenger: ReplayOutcomeSide
  delta: { hit_rate: number | null; skill: number | null; mean_signed_return_pct: number | null }
}

export interface ReplayChangedExample {
  signal_id: string
  symbol: string
  evaluated_at_ms: number
  change: 'admissions_gained' | 'admissions_lost' | 'direction_flips'
  baseline: string
  challenger: string
  baseline_coverage: number
  challenger_coverage: number
  has_outcome: boolean
}

export interface ReplayWindow {
  hours: ReplayHours
  horizon_minutes: ReplayHorizon
  symbol: string | null
  sample_bucket_seconds: number
  decisions_in_window: number
  refusals_in_window: number
  first_decision_at: string | null
  refusals_available_since: string | null
  refusal_retention_days: number
  skipped_unreplayable: number
}

export interface ReplayRulebook {
  rulebook_id: string
  version: string
  digest: string
  weights: Record<string, number>
  admitted: number
}

export interface ReplayJudgement {
  schema_version: 'regime_replay_judgement_v1'
  baseline: ReplayRulebook
  challenger: ReplayRulebook
  decisions: ReplayDecisionCounts
  outcomes: ReplayOutcomes
  changed_examples: ReplayChangedExample[]
  note: string
  window: ReplayWindow
  execution_authority: false
}

export interface RegimeLabExperimentRequest {
  name: string
  version: string
  hypothesis: string
  weights: Record<string, number>
  hours: ReplayHours
  horizon_minutes: ReplayHorizon
  symbol: string | null
}

export interface RegimeLabSaveResponse {
  saved: true
  experiment_id: string
  status: 'draft'
  replay: ReplayJudgement
  activation_available: false
}

export interface RegimeLabExperiment {
  id: string
  name: string
  status: string
  hypothesis: string
  created_at: string | null
  baseline_version: string
  challenger_version: string
  weights: Record<string, number | null>
  window_hours: ReplayHours | null
  horizon_minutes: ReplayHorizon | null
  symbol: string | null
  replay: { decisions: ReplayDecisionCounts; outcomes: ReplayOutcomes; window: ReplayWindow } | null
}

export interface RegimeLabExperimentList {
  experiments: RegimeLabExperiment[]
  count: number
}
