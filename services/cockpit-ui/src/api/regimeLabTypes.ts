// === Private Regime Lab ===

export interface RegimeLabFeatureResult {
  feature_id: string
  block: string
  unit: string
  provenance: string
  source_authority: string
  decision_role: string
  availability: string
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
  normalization?: {
    method: string
    center: number
    dispersion: number
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
  learning: {
    module: string
    class: string
    arithmetic_prompt: string
    interpretation_prompt: string
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
  operator_action_required: string
}

export interface RegimeLabExperimentRequest {
  name: string
  version: string
  hypothesis: string
  evaluation_window: string
  expected_effect: string
  weights: Record<string, number>
  arithmetic_answer: number
  reflection: string
  risk_flags: string[]
}

export interface RegimeLabEvaluationResponse {
  valid: boolean
  mode: 'paper_shadow'
  execution_authority: false
  hypothesis: string
  evaluation_window: string
  expected_effect: string
  weight_sum: number
  learning_gate: {
    arithmetic_passed: boolean
    reflection_recorded: boolean
    reflection_review: string
    complete: boolean
    note: string
  }
  block_evidence: Record<string, RegimeLabBlockEvidence>
  comparison: {
    baseline: RegimeEvaluation
    challenger: RegimeEvaluation
    score_delta: number
    same_market_evidence: true
    activation_authority: false
  }
  challenger_digest: string
  persistable: boolean
  activation_available: false
  source_status: RegimeLabOverview['source_status']
}

export interface RegimeLabExperimentList {
  experiments: Array<{
    id: string
    name: string
    status: string
    hypothesis: string
    baseline_version: string
    challenger_version: string
    created_at: string
  }>
  count: number
}
