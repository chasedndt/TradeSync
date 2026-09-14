import type { SkillGateCell, SkillGateResponse } from './outcomeEvidenceTypes'

export * from './regimeLabTypes'
export * from './outcomeEvidenceTypes'

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
  /** Where to read more: that day's ForexFactory calendar, or FRED's release calendar. */
  url?: string
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

// === Thesis (slice 6: the SOP's minimum valid thesis) ===

export interface ThesisLine {
  text: string
  source: string
  captured_at_ms: number | null
  age_ms: number | null
}

export interface ThesisAnchors {
  source?: string
  bucket_s: number
  candles: number
  note?: string
  last_close?: number | null
  last_open?: number | null
  high_1h?: number; low_1h?: number; covered_1h?: boolean
  high_4h?: number; low_4h?: number; covered_4h?: boolean
  high_24h?: number; low_24h?: number; covered_24h?: boolean
}

export interface ThesisStackItem {
  feature_id: string
  score: number | null
  reads: 'LONG' | 'SHORT' | 'flat'
  quality: number | null
  standing: 'scoring' | 'context_only' | 'unknown'
  earned: boolean
  earned_by: string[]
  entries_with_reading: number | null
}

export interface ThesisResponse {
  schema_version: 'thesis_v1'
  symbol: string
  generated_at_ms: number
  visibility: 'private'
  verdict: 'NO TRADE' | 'PAPER READ ONLY'
  freshness: { source_status: Record<string, unknown>; observation_age_ms: number | null; stale: boolean; stale_after_ms: number }
  structure: {
    entry_regime: string
    trailing_return_pct: number | null
    lookback_minutes: number | null
    direction: 'LONG' | 'SHORT' | 'NONE'
    directional_score: number | null
    signal_evaluated_at_ms: number | null
  }
  anchors: ThesisAnchors
  derivatives: {
    feature_id: string
    label: string
    value: number | null
    unit: string | null
    observed_at_ms: number | null
    age_ms: number | null
    status: string
    scoring_allowed: boolean
  }[]
  confirmation_stack: ThesisStackItem[]
  sources: { earned: { source_id: string; source: string; earned_by: string[] }[]; measured: number; recording: number }
  invalidation: { level: number | null; rule: string; source?: string }
  no_trade_conditions: { code: string; active: boolean; detail: string }[]
  confidence: { evidence_coverage: number | null; meaning: string }
  skill_gate: { gate: 'OPEN' | 'CLOSED' | null; any_economic_edge: boolean }
  upcoming_events: CalendarEvent[]
  lines: ThesisLine[]
  text: string
  note: string
}

// === Agents (Discord reader + advisory harness) ===

export interface HarnessStatus {
  status: 'not_configured' | 'offline' | 'live'
  url: string | null
  models: string[]
  detail?: string
  boundary: { may_explain: boolean; may_compare: boolean; may_draft_proposals: boolean; may_score: boolean; may_approve: boolean; may_execute: boolean }
  note: string
}

/** The payload the discord-reader files for one message (discord_message_v1). */
export interface DiscordMessagePayload {
  schema_version: 'discord_message_v1'
  kind: 'discord_message'
  agent: string
  channel_kind: 'agent' | 'alerts' | 'operator'
  channel_id: string
  message_id: string
  author: { id: string; name: string; bot: boolean }
  content: string
  content_truncated: boolean
  embeds: { title: string; description: string; url: string; fields: { name: string; value: string }[] }[]
  attachments: { filename: string; content_type: string; size: number | null; url: string }[]
  posted_at: string | null
  edited_at: string | null
}

/** The payload the host bridge files for one Hermes cron job run (hermes_job_output_v1). */
export interface HermesJobOutputPayload {
  schema_version: 'hermes_job_output_v1'
  kind: 'hermes_job_output'
  agent: string
  job_id: string
  job_enabled: boolean
  schedule: string
  delivery: { kind: string; channel_id: string | null; channel_label: string | null }
  ran_at_stamp: string
  content: string
  content_truncated: boolean
  filename: string
}

export type AgentPostPayload = DiscordMessagePayload | HermesJobOutputPayload

/** One horizon × polarity cell of a source card; same fields as a skill-gate cell. */
export interface SourceCardCell extends Omit<SkillGateCell, 'regime'> {
  polarity: 'as_stated' | 'inverted'
  earned: boolean
}

export interface SourceCard {
  source: 'tradingview' | 'discord' | 'chaseos' | string
  source_id: string
  claims: number
  claims_measured: number
  latest_claim_at: string | null
  cells: SourceCardCell[]
  earned: boolean
  earned_by: string[]
  next_step: string
}

export interface SourceCardsResponse {
  schema_version: 'source_cards_v1'
  symbol: string | null
  horizons: number[]
  polarities: ['as_stated', 'inverted']
  cards: SourceCard[]
  cells_assessed_together: number
  extraction: { rows_with_claims: number; rows_without_claims: number; rows_pending: number }
  costs: SkillGateResponse['costs']
  note: string
}

// === Hermes fleet (read model fed by the host bridge) ===

export interface FleetSchedule { kind?: 'interval' | 'cron'; minutes?: number; expr?: string; display?: string }

export interface FleetJob {
  state_source?: 'gateway' | 'bridge'
  gateway_missing?: boolean
  failure_streak?: number
  job_id: string
  name: string
  enabled: boolean
  schedule: FleetSchedule
  schedule_display: string
  deliver: string
  workdir: string | null
  script: string | null
  no_agent: boolean
  model: string | null
  description: string
  last_run_at: string | null
  last_status: string | null
  next_run_at: string | null
  state: string | null
  last_error?: string | null
  last_delivery_error?: string | null
  snapshot_at: string
  runs_24h: number
  failed_24h: number
  tokens_24h: number
  tokens_7d: number
  fires_7d: number
  pending_directives: { kind: string; payload: Record<string, unknown>; requested_at: string }[]
  /** The Discord target this job had before it was switched to TradeSync only. */
  restorable_deliver?: string | null
}

export interface FleetJobsResponse {
  live_state?: { source: 'gateway' | 'bridge'; status: string; observed_at: string | null; cache_seconds: number }
  schema_version: 'fleet_jobs_v1'
  jobs: FleetJob[]
  snapshot_at: string | null
  presets: Record<string, FleetSchedule>
  note: string
  control?: { gateway_api: boolean; gateway_status: string; note: string }
}

export interface FleetUsageResponse {
  schema_version: 'fleet_usage_v1'
  days: number
  daily: { day: string; fires: number; prompt_tokens: number; completion_tokens: number; total_tokens: number }[]
  by_job: { job_id: string; name: string; fires: number; total_tokens: number; avg_tokens: number; avg_duration_ms: number }[]
  runs: { runs?: number; failed?: number; completed?: number }
  note: string
}

export interface FleetDirective {
  id: string
  job_id: string
  name?: string | null
  kind: FleetDirectiveKind
  payload: Record<string, unknown>
  requested_by: string
  requested_at: string
  status: 'pending' | 'applied' | 'failed'
  applied_at: string | null
  previous: Record<string, unknown> | null
  detail: string
  /** "api": applied at once by the Hermes gateway's jobs API; "bridge": the host bridge edits jobs.json. */
  channel?: 'api' | 'bridge'
}

export type FleetDirectiveKind = 'set_schedule' | 'set_enabled' | 'set_workdir' | 'set_deliver' | 'pause' | 'resume' | 'run_now'

// === Thesis editions ===

export interface ThesisEdition {
  id: string
  edition: 'ny-premarket' | 'ny-midday' | 'session-handoff' | 'manual'
  generated_at: string
  symbols: string[]
  headline: string
  text: string
  narration: string
  verdicts: Record<string, string>
  media: Record<string, string>
  trigger: string
  schema_version: string
  theses?: Record<string, ThesisResponse>
  /** Empty object on editions made before the outlook existed. */
  outlook: MarketOutlook | Record<string, never>
  briefing: HermesBriefing | Record<string, never>
  reason: string
}

export interface EditionGeneration {
  running: boolean
  stage: string
  edition: string | null
  reason: string
  trigger: string | null
  started_at: string | null
  finished_at: string | null
  last_error: string | null
  last_id: string | null
}

export interface ThesisEditionsResponse {
  schema_version: 'thesis_editions_v2'
  editions: ThesisEdition[]
  generation: EditionGeneration
  schedule: { timezone: string; entries: string; enabled: boolean; next: { edition: string | null; at: string | null } }
}

export interface EventReactionHorizon {
  n: number
  median_abs_move_pct: number | null
  median_range_pct: number | null
  baseline_median_abs_move_pct: number | null
  baseline_days: number
  volatility_ratio: number | null
  up_share: number | null
  mean_move_pct: number | null
}

export interface OutlookArticle { title: string; url: string; domain: string; seen: string }

export interface OutlookKeyEvent {
  title: string
  country: string | null
  impact: string | null
  scheduled_at: string
  minutes_until: number
  source: string | null
  url: string | null
  forecast?: string | null
  previous?: string | null
  kind: string | null
  kind_label: string | null
  /** symbol -> horizon ("1h" | "4h" | "24h") -> measured reaction */
  reaction: Record<string, Record<string, EventReactionHorizon>>
  guidance: string[]
  articles: OutlookArticle[]
  /** Other titles for the same release at the same instant, merged into this event. */
  related_titles?: string[]
}

export interface MarketOutlook {
  schema_version: 'market_outlook_v1'
  generated_at: string
  breadth: {
    lean: 'bearish' | 'bullish' | 'mixed' | 'none'
    summary: string
    reads: { LONG: number; SHORT: number; NONE: number }
    regimes: Record<string, number>
    verdicts: Record<string, number>
    meaning: string
  }
  leads: {
    symbol: string
    direction: string | null
    regime: string | null
    verdict: string | null
    last: number | null
    low_24h: number | null
    high_24h: number | null
    invalidation: number | null
    coverage: number | null
  }[]
  key_events: OutlookKeyEvent[]
  notes: string[]
  reaction_method: { measure: string; baseline: string; window: Record<string, unknown>; caveat: string }
}

export interface HermesBriefing {
  status: 'ok' | 'refused' | 'unavailable' | 'not_configured'
  content?: string
  model?: string
  elapsed_ms?: number
  detail?: string
  receipt?: { content_digest?: string }
  authority?: string
  source?: string
}

export interface EventReactionsResponse {
  schema_version: 'event_reactions_v1'
  computed_at: string | null
  computing: boolean
  window: Record<string, unknown>
  errors: string[]
  kinds: Record<string, { label: string; source_url: string }>
  key_events: OutlookKeyEvent[]
  note: string
}

export interface HermesLinkStatus {
  status: 'live' | 'degraded' | 'offline' | 'checking' | 'not_configured'
  name: string
  url: string | null
  host: string | null
  port: number | null
  api: string
  version: string | null
  platform: string | null
  last_seen_at: string | null
  seconds_since_seen: number | null
  last_check_at: string | null
  latency_ms: number | null
  consecutive_failures: number
  last_error: string | null
  models: string[]
  models_ok: boolean | null
  models_error: string | null
  heartbeat_s: number
  availability_recent: number | null
  checks: { at: string; ok: boolean; latency_ms?: number; error?: string }[]
  watching_since: string | null
  gateway: {
    payload: {
      gateway_state?: string
      pid?: number
      code_version?: string
      active_agents?: number
      updated_at?: string
      platforms?: Record<string, { state: string; error_message?: string | null; updated_at?: string }>
    }
    source_updated_at: string | null
    snapshot_at: string
  } | null
  boundary: Record<string, boolean>
}

// === Paper rehearsal ===

export interface RehearseRequest {
  opportunity_id: string
  size_usd: number
}

export interface SimulatedFill {
  direction: 'LONG' | 'SHORT'
  size_usd: number
  mark_price: number
  fill_price: number
  quantity: number
  half_spread_bps: number
  slippage_usd: number
  fee_usd: number
  entry_cost_usd: number
  /** Move needed in the called direction to cover entry costs alone. */
  breakeven_move_pct: number
  observed_at_ms: number
  fees: { taker_fee: number; maker_fee: number; source: string; read_on: string }
  simulated: true
  note: string
}

export interface RehearsalRecord {
  id: string
  opportunity_id: string
  symbol: string
  direction: 'LONG' | 'SHORT'
  size_usd: number
  status: 'rehearsed' | 'refused'
  plan: Record<string, unknown>
  risk_verdict: { allowed: boolean; reason_code: string; reason: string }
  fill: SimulatedFill | null
  market: { mark_price_usd?: number; spread_bps?: number; snapshot_ts?: number; snapshot_age_ms?: number | null }
  created_at: string
  note: string
}

export interface RehearseResponse {
  duplicate: boolean
  rehearsal: RehearsalRecord
}

export interface RehearsalListResponse {
  rehearsals: RehearsalRecord[]
  counts: { rehearsed: number; refused: number }
  execution_authority: false
  note: string
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
  /** What extraction made of it: the rule pass, and the harness pass if it was asked. */
  extraction?: {
    rule: { claims: number; reason: string } | null
    harness: { claims: number; reason: string } | null
  }
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
