/** Response shapes for opportunity learning (services/state-api/app/learning_routes.py). */

export type Classification = 'clean_win' | 'win_after_drawdown' | 'wrong_direction' | 'reversed' | 'no_follow_through'
export type ReadingVerdict = 'supported' | 'misled' | 'neutral'
export type GroupVerdict = 'helping' | 'hurting' | 'no_evidence'
export type ProposalStatus = 'proposed' | 'adopted' | 'rejected' | 'superseded'

export interface AttributedReading {
  id: string
  label: string
  block: string
  role: 'directional' | 'suitability'
  score: number
  quality: number
  weight: number
  contribution: number
  stance: 'with' | 'against' | 'none'
  verdict: ReadingVerdict
}

export interface Attribution {
  opportunity_id: string
  horizon_minutes: number
  symbol: string
  direction: 'LONG' | 'SHORT'
  opened_at: string
  classification: Classification
  reason: string
  signed_return_pct: number
  net_return_pct: number
  cost_pct: number
  max_favourable_pct: number | null
  max_adverse_pct: number | null
  entry_regime: string
  features: AttributedReading[]
  blocks: AttributedReading[]
  rulebook_version: string | null
}

export interface DailyScore {
  day: string
  attributions: number
  net_hit_rate: number | null
  mean_net_return_pct: number | null
}

export interface HorizonScore {
  horizon_minutes: number
  attributions: number
  effective_samples: number
  wins: number
  net_hit_rate: number | null
  net_hit_rate_low: number | null
  net_hit_rate_high: number | null
  mean_net_return_pct: number | null
  mean_net_return_low: number | null
  mean_net_return_high: number | null
  classifications: Record<Classification, number>
  daily: DailyScore[]
}

export interface ScoreboardResponse {
  days: number
  cost_pct: number
  attributions: number
  horizons: HorizonScore[]
  note: string
}

export interface GroupEvidence {
  dimension: string
  key: string
  label: string
  role: string | null
  horizon_minutes: number
  decided: number
  supported: number
  misled: number
  neutral: number
  misled_rate: number | null
  misled_low: number | null
  misled_high: number | null
  chance_misled_rate: number | null
  effective_samples: number
  mean_net_return_pct: number | null
  mean_net_agreed_pct: number | null
  agreed: number
  mean_net_disagreed_pct: number | null
  disagreed: number
  verdict: GroupVerdict
}

export interface VerdictsResponse {
  horizon_minutes: number
  days: number
  attributions: number
  policy: { min_decided: number; min_effective: number; z: number }
  feature: GroupEvidence[]
  block: GroupEvidence[]
  regime: GroupEvidence[]
  symbol: GroupEvidence[]
}

export interface ReplayMetrics {
  rulebook_version: string
  decisions: number
  admitted: number
  refused: number
  flipped: number
  unreplayable: number
  reproduced_share: number | null
  effective_samples: number
  net_hit_rate: number | null
  net_hit_rate_low: number | null
  net_hit_rate_high: number | null
  mean_net_return_pct: number | null
  mean_net_return_low: number | null
  mean_net_return_high: number | null
}

export interface WeightChange { before: number; after: number; verdict: GroupVerdict }

export interface WindowSpan { decisions: number; first_opened_at_s: number | null; last_opened_at_s: number | null; purged?: number }

export interface Proposal {
  id: string
  status: ProposalStatus
  target_horizon_minutes: number
  parent_version: string
  version: string
  hypothesis: string
  weights: { blocks?: Record<string, WeightChange>; features?: Record<string, WeightChange> }
  evidence: { window?: { learn: WindowSpan; test: WindowSpan }; guardrails?: Record<string, unknown>; cost_pct?: number }
  replay: { baseline?: ReplayMetrics; proposal?: ReplayMetrics; assessment?: string; note?: string }
  cost_pct: number
  created_by: string
  created_at: string
  decided_at: string | null
  decided_by: string | null
  decision_note: string
  reverted_at: string | null
}

export interface ProposalsResponse {
  proposals: Proposal[]
  last_run?: { reason?: string; proposal_id?: string | null; at?: string; error?: string } | null
}

export interface ActiveRulebookResponse {
  active: {
    source: 'database' | 'file'
    version: string
    digest: string
    weights: Record<string, number>
    feature_weights: Record<string, number>
    activated_at: string | null
    activated_by: string | null
    reason: string
  }
  file: { version: string; digest: string }
  scorer_last_used: { at: string; version: string | null; digest: string | null } | null
  scorer_in_step: boolean
}

export interface GenerateResponse { reason: string; proposal_id: string | null; decisions: number; assessment?: string }

export interface OutcomeRow {
  horizon_minutes: number
  status: string
  entry_price: number | null
  exit_price: number | null
  signed_return_pct: number | null
  max_favourable_pct: number | null
  max_adverse_pct: number | null
  reason: string
}

export interface OpportunityAttributionResponse {
  opportunity_id: string
  entry_regime: { regime: string; trailing_return_pct: number | null } | null
  outcomes: OutcomeRow[]
  attributions: Attribution[]
}

export interface LifecycleResponse {
  live: number
  ttl_seconds: number
  window_minutes: number
  last_opportunity: { id: string; symbol: string; direction: string; opened_at: string | null; expires_at: string | null } | null
  verdicts: { total: number; admitted: number; refused: number; last_verdict_at: string | null }
  top_refusal_reasons: { code: string; label: string; refusals: number; share_of_refusals: number | null; example_detail: string | null }[]
  note: string
}
