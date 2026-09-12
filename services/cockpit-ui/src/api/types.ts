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

export interface PriceData {
  mark_price_usd: number
  oracle_price_usd: number
  oracle_premium_bps: number
  /** Venue-published previous-day reference; null when Hyperliquid omits it. */
  prev_day_price_usd?: number | null
  /** Derived from mark and prev_day only. Null means unavailable, not zero. */
  change_24h_pct?: number | null
}

export interface MarketSnapshot {
  venue: string
  symbol: string
  ts: number
  /**
   * Time since the venue was last observed for this symbol — liveness.
   * Distinct from data_age_ms, the age of the oldest metric inside the
   * snapshot — completeness. Judge "is the feed alive" on this one.
   */
  snapshot_age_ms?: number | null
  data_age_ms: number
  available_metrics: MetricAvailability[]
  price?: PriceData
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

/** One scheduled economic event, already validated and converted to UTC. */
export interface CalendarEvent {
  title: string
  country: string
  impact: 'High' | 'Medium' | 'Low' | 'Holiday'
  /** ISO 8601, UTC. FRED rows are date-only: midnight UTC of that date. */
  scheduled_at: string
  minutes_until: number
  source: 'forexfactory' | 'fred'
  forecast: string
  previous: string
  /** By title (FOMC, CPI, NFP…), not by the feed's own impact rating. */
  market_moving: boolean
}

export interface CalendarProviderData {
  metric_family?: 'economic_calendar'
  events?: CalendarEvent[]
  next_market_moving?: CalendarEvent | null
  counts?: { total: number; high: number; market_moving: number; rejected: number }
  rejections?: string[]
  sources?: string[]
  fred_configured?: boolean
}

export interface ContextOverviewResponse {
  role: 'context_only'
  authoritative_market_source: 'hyperliquid'
  execution_venue: 'hyperliquid'
  execution_authority: false
  providers: Record<'coingecko' | 'defillama' | 'fred', ContextProvider> & {
    calendar?: Omit<ContextProvider, 'data'> & { data: CalendarProviderData }
  }
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

// === Integration Pipeline ===

export type PipelineNodeStatus =
  | 'live'
  | 'healthy'
  | 'partial'
  | 'offline'
  | 'contract_only'
  | 'planned'
  | 'locked'

export interface PipelineRecovery {
  kind: string
  label: string
  target: string
  command?: string | null
}

export interface PipelineNode {
  id: string
  label: string
  owner: string
  tier: string
  stage: string
  status: PipelineNodeStatus
  required_for_tier_a: boolean
  authority: string
  summary: string
  evidence: string[]
  missing: string[]
  impact: string
  recovery: PipelineRecovery
  /** How long this stage has held its current state. Null when unrecorded. */
  state_since_epoch_s?: number | null
  state_duration_seconds?: number | null
  /** Coarse phrasing, e.g. "2h 15m" or "unknown". */
  state_age?: string
  /** State changes in the last 15 minutes. */
  recent_transitions?: number
  /** Oscillating rather than settled: read the current state with suspicion. */
  flapping?: boolean
}

export interface PipelineRecoveryItem {
  node_id: string
  label: string
  status: PipelineNodeStatus
  required_for_tier_a: boolean
  missing: string[]
  impact: string
  recovery: PipelineRecovery
}

export interface IntegrationPipelineStatus {
  schema_version: 'integration_pipeline_status_v1'
  generated_at: string
  mode: 'paper'
  execution_authority: false
  tier_a: {
    status: 'ready' | 'partial' | 'offline'
    ready_count: number
    total_count: number
    principle: string
  }
  federated: {
    status: 'connected' | 'not_connected'
    connected_count: number
    total_count: number
  }
  nodes: PipelineNode[]
  edges: Array<{
    from: string
    to: string
    label: string
    status: 'flowing' | 'partial' | 'not_connected' | 'locked'
  }>
  recovery_queue: PipelineRecoveryItem[]
  capability_gaps: Array<{
    id: string
    status: string
    blocking: string
    next_action: string
  }>
}

export interface Candle {
  /** UNIX seconds, as the charting library expects. */
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface CandleResponse {
  venue: string
  symbol: string
  interval: string
  requested: number
  count: number
  candles: Candle[]
  /** Always "display_only" — candles are not catalog features. */
  authority: string
}

/** One value collapsed onto a candle open. */
export interface ContextPoint {
  /** UNIX seconds, aligned to the candle open. */
  time: number
  value: number
  /** How many raw samples fell in this bucket. */
  samples: number
}

/**
 * How much of the chart window a series actually covers.
 *
 * Reported rather than inferred: a line that stops has either run out of
 * recording or run into a collection gap, and those are different problems.
 */
export interface ContextCoverage {
  candles: number
  covered: number
  coverage_pct: number
  first_time: number | null
  last_time: number | null
}

export interface ContextSeries {
  series: ContextPoint[]
  unit: string
  source: string
  coverage: ContextCoverage
  /** Funding only: it is published hourly whatever the chart interval. */
  native_period_s?: number
  /** Open interest only: states why the series cannot reach further back. */
  limit_note?: string
}

export interface MarketContextResponse {
  venue: string
  symbol: string
  interval: string
  bucket_s: number
  funding: ContextSeries
  open_interest: ContextSeries
  /** Always "display_only". */
  authority: string
}

export interface DepthLevel {
  price: number
  size: number
  notional_usd: number
  /** Running notional outward from the touch: the cost to sweep to here. */
  cumulative_usd: number
  orders: number
}

/** A level holding an outsized share of its own side's visible notional. */
export interface RestingWall {
  side: 'bid' | 'ask'
  price: number
  notional_usd: number
  share_of_side: number
}

export interface DepthResponse {
  venue: string
  symbol: string
  poll_ts: number
  best_bid: number
  best_ask: number
  mid_price: number
  spread_bps: number
  imbalance_1pct: number
  depth: {
    bid_1pct_usd: number
    ask_1pct_usd: number
    bid_2pct_usd: number
    ask_2pct_usd: number
  }
  bids: DepthLevel[]
  asks: DepthLevel[]
  walls: RestingWall[]
  /** Always "display_only". */
  authority: string
}

export interface QuarantineReason {
  code: string
  detail: string
}

export interface QuarantineItem {
  id: string
  source: string
  /** Whether it passed intake. Acceptance confers no authority. */
  accepted: boolean
  content_digest: string
  payload: Record<string, unknown>
  reasons: QuarantineReason[]
  observed_at: string | null
  received_at: string
  reviewed_by: string | null
  /** Null until an operator promotes it. Promotion is never automatic. */
  promoted_to: string | null
}

export interface QuarantineList {
  schema_version: string
  /** Always "none" — quarantined material carries no authority. */
  authority: string
  items: QuarantineItem[]
  note: string
}

export interface QuarantineReviewResult {
  id: string
  reviewed_by: string
  promoted: boolean
  blockers: QuarantineReason[]
  authority: string
  note: string
}

export interface DrawingPoint {
  /** UNIX seconds, matching the chart. */
  time_s: number
  price: number
}

export type DrawingKind = 'horizontal' | 'trendline' | 'range' | 'note'

export interface DrawingInput {
  symbol: string
  interval: string
  kind: DrawingKind
  points: DrawingPoint[]
  label?: string
  colour?: string
}

export interface Drawing extends DrawingInput {
  drawing_id: string
  /** Increments on every edit; earlier versions are retained server-side. */
  version: number
  created_at?: string
  /** Always "none" — a drawing is annotation, never evidence. */
  authority?: string
}

export interface DrawingList {
  schema_version: string
  symbol: string
  interval: string
  authority: string
  drawings: Drawing[]
}

export interface TimelineOutcome {
  horizon_minutes: number
  status: 'measured' | 'pending' | 'insufficient_candles'
  signed_return_pct: number | null
  forward_return_pct: number | null
  max_favourable_pct: number | null
  max_adverse_pct: number | null
}

export interface TimelineFeature {
  feature_id: string
  score: number
  data_quality: number
  block?: string
}

export interface TimelineEntry {
  opportunity_id: string
  signal_id: string | null
  symbol: string
  direction: string
  directional_score: number
  coverage_pct: number
  opened_at: string
  signal_at: string | null
  /** Digests pin the exact configuration, so a replay reproduces it exactly. */
  catalog_version: string | null
  catalog_digest: string | null
  rulebook_version: string | null
  rulebook_digest: string | null
  evidence_digest: string | null
  contributing_features: TimelineFeature[]
  missing_blocks: string[]
  paper_risk_multiplier: number | null
  outcomes: TimelineOutcome[]
}

export interface EvidenceTimeline {
  schema_version: string
  symbol: string
  entries: TimelineEntry[]
  note: string
}
