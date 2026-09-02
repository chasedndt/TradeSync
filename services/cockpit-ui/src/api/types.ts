export interface HealthResponse {
  status: string
  postgres: boolean
  last_event_ts: string | null
  last_signal_ts: string | null
  latency_ms: number
}

export interface SnapshotResponse {
  latest_event_ts: string | null
  latest_signal_ts: string | null
  latest_opportunity_ts: string | null
  execution_gate: string
  hl_status: string
  hl_circuit: CircuitStatus | null
  stream_lengths: Record<string, number>
  ingest_sources: IngestSource[]
}

export interface CircuitStatus {
  venue: string
  circuit_open: boolean
  fail_count: number
  last_fail_reason?: string
  last_fail_ts?: string
}

export interface IngestSource {
  source: string
  symbols: string[]
  interval_sec: number
  last_poll_ts?: string
}

export interface Opportunity {
  id: string
  symbol: string
  timeframe: string
  bias: number
  quality: number
  dir: string
  status: string
  snapshot_ts: string
  links: Record<string, unknown>
}

export interface Signal {
  id: string
  created_at: string
  agent: string
  symbol: string
  timeframe: string
  kind: string
  confidence: number
  dir: string
  features: Record<string, unknown>
}

export interface Event {
  id: string
  ts: string
  source: string
  kind: string
  symbol: string
  timeframe: string
  payload: Record<string, unknown>
}

export interface Decision {
  id: string
  opportunity_id?: string
  venue: string
  requested: Record<string, unknown>
  risk: Record<string, unknown>
}

export interface ExecOrder {
  id: string
  decision_id: string
  venue: string
  status: string
  request: Record<string, unknown>
  response: Record<string, unknown>
  dry_run: boolean
}

export interface EvidenceResponse {
  opportunity: Opportunity | null
  signals: Signal[]
  events: Event[]
  decisions: Decision[]
  exec_orders: ExecOrder[]
}

export interface Position {
  venue: string
  symbol: string
  side: string
  size_usd: number
  entry_price: number
  mark_price: number
  pnl_usd: number
  leverage: number
  timestamp: string
}

export interface RiskLimitResponse {
  max_leverage: number
  min_quality: number
  max_open_positions: number
  min_size_usd: number
  max_event_age: number
  max_signal_age: number
  blacklist: string[]
  daily_notional_limit: number
  current_counters: {
    daily_notional_usage: number
    today_date: string
  }
}

export interface PreviewRequest {
  opportunity_id: string
  size_usd: number
  venue: string
}

export interface PreviewResponse {
  decision_id: string | null
  plan: Record<string, unknown>
  risk_verdict: {
    allowed: boolean
    reason: string
    checks: Record<string, boolean>
  }
  suggested_adjustments: Record<string, unknown> | null
}

export interface ExecuteRequest {
  decision_id: string
  confirm: boolean
}

export interface ExecutionResult {
  ok: boolean
  venue: string
  dry_run: boolean
  execution_enabled: boolean
  status: 'placed' | 'rejected' | 'error'
  order_id: string | null
  idempotency_key: string
  request_payload: Record<string, unknown>
  response_payload: Record<string, unknown>
  error: { code: string; message: string } | null
  ts: string
}

export interface ExecutionStatus {
  execution_enabled: string
  venues: VenueStatus[]
}

export interface VenueStatus {
  venue: string
  circuit_open: boolean | string
  fail_count?: number
  error?: string
}

// === Market Data Types (Phase 3B) ===

export type MetricStatus = 'REAL' | 'PROXY' | 'UNAVAILABLE' | 'STALE'

export interface MetricAvailability {
  metric: string
  status: MetricStatus
  source?: string
  last_updated?: number
  note?: string
}

export interface FundingHorizons {
  now: number
  h8: number
  h24: number
  d3: number
  d7: number
}

export interface FundingData {
  horizons: FundingHorizons
  annualized_24h: number
  regime: string
  source: {
    provider: string
    endpoint: string
    raw_rate: number
  }
}

export interface HorizonValue {
  value: number
  delta_pct: number
  delta_usd: number
}

export interface OpenInterestData {
  horizons: Record<string, HorizonValue>
  current_usd: number
  regime: string
}

export interface LiquidationWindow {
  longs_usd: number
  shorts_usd: number
  total_usd: number
  dominant_side: string
}

export interface LiquidationData {
  horizons: Record<string, LiquidationWindow>
  source_note?: string
  method: string
}

export interface OrderbookData {
  spread_bps: number
  spread_usd: number
  depth: {
    bid_1pct_usd: number
    ask_1pct_usd: number
    bid_2pct_usd: number
    ask_2pct_usd: number
  }
  imbalance_1pct: number
  best_bid: number
  best_ask: number
  mid_price: number
  book_age_ms: number
}

export interface VolumeData {
  horizons: Record<string, number>
  cvd?: Record<string, number>
  cvd_method?: string
  avg_7d_daily: number
  regime: string
}

export interface RegimeSummary {
  funding: string
  oi: string
  volume: string
  trend: string
  market_condition: string
  confidence: string
  confidence_note?: string
}

export interface MarketSnapshot {
  venue: string
  symbol: string
  ts: number
  data_age_ms: number
  available_metrics: MetricAvailability[]
  funding?: FundingData
  oi?: OpenInterestData
  liquidations?: LiquidationData
  volume?: VolumeData
  orderbook?: OrderbookData
  regimes: RegimeSummary
  sources: Array<{
    provider: string
    endpoint: string
    fetched_at: number
    metrics_provided: string[]
  }>
}

export interface MarketAlert {
  id: string
  venue: string
  symbol: string
  ts: number
  alert_type: string
  metric: string
  previous_value?: string
  new_value: string
  context: Record<string, unknown>
}

export interface MarketDataStatus {
  status?: string
  providers: Array<{
    venue: string
    enabled: boolean
    metrics: string[]
  }>
  symbols: string[]
  rate_limiters?: Record<string, unknown>
}

// === Phase 3C: Microstructure Types ===

export interface BookHeatmapLevel {
  price: number
  side: 'bid' | 'ask'
  size_usd: number
}

export interface MicrostructureData {
  spread_bps: number
  mid_price: number
  depth_usd: Record<string, number>  // Keys: "10bp", "25bp", "50bp"
  impact_est_bps: Record<string, number>  // Keys: "1000", "5000", "10000" (USD sizes)
  liquidity_score: number
  book_heatmap: BookHeatmapLevel[]
}

export interface ExecutionRisk {
  spread_bps: number
  impact_est_bps_5k: number
  depth_25bp: number
  liquidity_score: number
  flags: string[]
}

export interface ScoreBreakdown {
  alpha: number
  microstructure_penalty: number
  exposure_penalty: number
  regime_bonus: number
  final_score: number
  notes: string[]
}

export interface Confluence {
  score_breakdown: ScoreBreakdown
  execution_risk: ExecutionRisk
  warnings: string[]
}

// Extended Opportunity with Phase 3C confluence data
export interface OpportunityWithConfluence extends Opportunity {
  confluence?: Confluence
}

// Extended MarketSnapshot with Phase 3C microstructure
export interface MarketSnapshotWithMicrostructure extends MarketSnapshot {
  microstructure?: MicrostructureData
}

// === Phase 3C: Macro Feed Types ===

export interface MacroHeadline {
  title: string
  source: string
  category: string
  url: string
  published_at?: string
  summary?: string
  sentiment?: 'bullish' | 'bearish' | 'neutral'
}

export interface MacroFeedStatus {
  sources_configured: number
  headlines_cached: number
  cache_age_seconds?: number
  cache_ttl_seconds: number
  sources: string[]
  error?: string
}

export interface MacroFeedResponse {
  headlines: MacroHeadline[]
  status: MacroFeedStatus
  cached: boolean
  ts: string
}

export interface ContextProvider {
  provider: string
  status: 'healthy' | 'stale' | 'degraded' | 'unavailable' | 'disabled'
  source_type: 'context_only'
  execution_authority: false
  cached?: boolean
  stale?: boolean
  age_seconds?: number | null
  fetched_at?: string | null
  ttl_seconds?: number
  reason?: string
  error?: string
  data: {
    metric_family?: string
    assets?: Record<string, {
      price_usd: number
      change_24h_pct?: number | null
      observed_at?: number
    }>
    protocol?: string
    tvl_usd?: number
    series?: Record<string, { value: string; date: string }>
  }
}

export interface ContextOverviewResponse {
  role: 'context_only'
  authoritative_market_source: 'hyperliquid'
  execution_venue: 'hyperliquid'
  execution_authority: false
  providers: Record<'coingecko' | 'defillama' | 'fred', ContextProvider>
  generated_at: string
}

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
