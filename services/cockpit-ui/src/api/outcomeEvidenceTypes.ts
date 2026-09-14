// === Skill gate (corrected measurement) ===

export interface SkillGateCell {
  label: string
  horizon_minutes: number
  regime: 'rising' | 'falling' | 'flat' | 'unknown'
  measured: number
  independent_per_symbol: number
  independent_pooled: number
  hit_rate: number | null
  expected_hit_rate: number | null
  skill: number | null
  standard_error: number | null
  z: number | null
  /** |z| >= 2 in either direction: the sample can tell this apart from zero. */
  detectable: boolean
  /** skill > 0, Holm-adjusted across every cell assessed together, and z >= 2. */
  positive_skill: boolean
  /** null when costs were not supplied; never false by default. */
  economic_edge: boolean | null
  mean_signed_return_pct: number | null
  mean_net_return_pct: number | null
  in_sample_skill: number | null
  holdout_skill: number | null
  holdout_measured: number
  notes: string[]
  readiness: string
}

export interface SkillGateResponse {
  schema_version: 'skill_gate_v2'
  symbol: string | null
  horizons: number[]
  cells: SkillGateCell[]
  cells_assessed_together: number
  verdict: { any_detectable: boolean; any_positive_skill: boolean; any_economic_edge: boolean; gate: 'OPEN' | 'CLOSED' }
  costs: { round_trip_fee_pct: number; spread_pct: number; slippage_pct: number; total_pct: number; source: string }
  entry_regimes_pending: number
  note: string
}

// === Evidence cards (slice 5: earned weights) ===

export type EvidencePolarity = 'as_read' | 'inverted'

/** One horizon x polarity cell of a feature card; same fields as a skill-gate cell. */
export interface EvidenceCardCell extends Omit<SkillGateCell, 'regime'> {
  polarity: EvidencePolarity
  /** positive skill that also held on the chronological hold-out */
  earned: boolean
}

export interface EvidenceCard {
  feature_id: string
  standing: 'scoring' | 'context_only'
  block: string | null
  unit: string | null
  provenance: string | null
  source_authority: string | null
  decision_role: string | null
  cells: EvidenceCardCell[]
  earned: boolean
  earned_by: string[]
  abstained: number
  entries_with_reading: number
  entries_without_reading: number
  next_step: string
  meaning: string
}

export interface EvidenceCardsResponse {
  schema_version: 'evidence_cards_v1'
  symbol: string | null
  catalog_version: string
  horizons: number[]
  polarities: EvidencePolarity[]
  cards: EvidenceCard[]
  cells_assessed_together: number
  entries_pending: number
  costs: SkillGateResponse['costs']
  note: string
}

// === Slow readings served from the statistics cache ===

export interface CacheState {
  age_s: number | null
  ttl_s: number
  stale: boolean
  refreshing: boolean
  duration_s: number | null
  last_error: string | null
}

/** A measured reading: its body, when it was computed, and the cache's view of it. */
export interface MeasuredReading {
  status: 'ready'
  computed_at: string
  cache: CacheState
}

/** A market not measured yet; the API is measuring it behind the request. */
export interface ComputingReading {
  schema_version: string
  status: 'computing'
  symbol: string | null
  computed_at: null
  cache: CacheState
  note: string
}

export type SkillGateReading = (SkillGateResponse & MeasuredReading) | ComputingReading
export type EvidenceCardsReading = (EvidenceCardsResponse & MeasuredReading) | ComputingReading
