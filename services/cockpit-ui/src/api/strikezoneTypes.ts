/** The StrikeZone quant lab as the state API serves it. Paper-only research; nothing here grants authority. */

export type LabDirection = 'long' | 'short' | 'no_trade'
export type LabStatus = 'no_trade' | 'resolved' | 'open' | 'resolving' | 'overdue'
export type LedgerView = 'trades' | 'all' | 'open' | 'resolved' | 'no_trade'

export interface LabTradeRef {
  direction: LabDirection
  signal_at: string | null
  entry_price: number | null
  invalidation_price: number | null
  target_price: number | null
  status: LabStatus
}

export interface LabCell {
  asset: string
  timeframe: string
  last_signal_at: string | null
  age_minutes: number | null
  stale_after_minutes: number
  stale: boolean
  last_direction: LabDirection | null
  last_confidence: number | null
  last_trade: LabTradeRef | null
  calls_24h: number
  trades_24h: number
  open_trades: number
  resolved_7d: number
  wins_7d: number
  win_rate_7d: number | null
  net_7d: number
}

export interface LabEquity {
  points: { t: string; cumulative: number; n: number }[]
  trades: number
  net_pnl_usdc: number
  win_rate: number | null
  max_drawdown_usdc: number
}

export interface ForwardTestResponse {
  schema_version: 'strikezone_forward_test_v1'
  methodology_version: string | null
  strategy_version: string | null
  assets: string[]
  timeframes: string[]
  cells: LabCell[]
  totals: {
    signals: number
    trades: number
    outcomes: number
    open: number
    resolving: number
    overdue: number
    last_signal_at: string | null
    last_signal_age_minutes: number | null
    last_outcome_at: string | null
  }
  equity: LabEquity
  paper_notional_usdc: number | null
  note: string
}

export interface LabOutcome {
  outcome_id: string
  exit_reason: string | null
  exit_at: string | null
  holding_minutes: number | null
  net_pnl_usdc: number | null
  gross_pnl_usdc: number | null
  fees_usdc: number | null
  slippage_usdc: number | null
  funding_usdc: number | null
  entry_fill_price: number | null
  exit_fill_price: number | null
  chart_url: string | null
}

export interface LedgerRow {
  signal_id: string
  asset: string
  timeframe: string
  direction: LabDirection
  signal_at: string | null
  expiry_at: string | null
  confidence: number | null
  entry_price: number | null
  invalidation_price: number | null
  target_price: number | null
  planned_reward_risk: number | null
  regime: Record<string, string>
  status: LabStatus
  chart_url: string | null
  outcome: LabOutcome | null
}

export interface LedgerResponse {
  schema_version: 'strikezone_ledger_v1'
  methodology_version: string | null
  filters: { asset: string | null; timeframe: string | null; view: LedgerView; limit: number }
  rows: LedgerRow[]
  note: string
}

export interface LabResults {
  trades: number
  wins: number
  losses: number
  net_pnl_usdc: number | null
}

export interface ScorecardRow {
  asset: string
  timeframe: string
  maturity: string
  score_withheld_reason: string | null
  win_rate_percentage: number | null
  net_pnl_usdc: number | null
  expectancy_usdc_per_trade: number | null
  profit_factor: number | null
  maximum_drawdown_usdc: number | null
  total_fees_usdc: number | null
  total_slippage_usdc: number | null
  total_funding_cost_usdc: number | null
  average_holding_minutes: number | null
  resolved_trades: number
  wins: number
  losses: number
  correlation_adjusted_sample: number
  independent_day_count: number
  independent_regime_count: number
  minimum_sample: number
  minimum_independent_days: number
  minimum_independent_regimes: number
  brier_score: number | null
  average_confidence: number | null
  realized_win_rate: number | null
  rolling_7d: LabResults | null
  direction_results: Record<string, LabResults>
  session_results: Record<string, LabResults>
  regime_results: Record<string, LabResults>
  exit_reason_counts: Record<string, number>
}

export interface CohortRow {
  asset: string | null
  timeframe: string | null
  utc_session: string | null
  trend_range_regime: string | null
  volatility_bucket: string | null
  event_proximity: string | null
  sample_adequacy: string | null
  resolved_trades: number
  wins: number
  losses: number
  independent_sample: number
  minimum_independent_sample: number
  win_rate_percentage: number | null
  net_pnl_usdc: number | null
  expectancy_usdc_per_trade: number | null
}

export interface LabRegime {
  cohorts: CohortRow[]
  aggregate: CohortRow | null
  minimum_independent_sample: number | null
}

export interface LabAssumptions {
  paper_notional_usdc: number | null
  entry_fee_rate: number | null
  exit_fee_rate: number | null
  adverse_slippage_bps_each_fill: number | null
  liquidity: string
  funding_cost_model: string | null
  minimum_scorecard_sample: number | null
  note: string | null
}

export interface ScorecardsResponse {
  schema_version: 'strikezone_scorecards_v1'
  generated_at: string | null
  methodology_version: string | null
  snapshot_at: string | null
  ranking_policy: { minimum_independent_events_per_asset_timeframe?: number; rankings_withheld_below_floor?: boolean } | null
  scorecards: ScorecardRow[]
  regime: LabRegime
  assumptions: LabAssumptions | null
  note: string
}

export interface LabJob {
  job_id: string
  name: string
  enabled: boolean
  schedule_display: string
  last_status: string | null
  last_run_at: string | null
  next_run_at: string | null
  overdue: boolean
  runs_24h: number
  failed_24h: number
  diagnosis: string | null
  error_excerpt: string | null
  delivery_problem: string | null
}

export interface LabHealthResponse {
  schema_version: 'strikezone_health_v1'
  ok: boolean | null
  checked_at: string | null
  checked_age_minutes: number | null
  issues: { code: string; text: string }[]
  counts: {
    signal_records: number
    paper_candidates: number
    resolved_outcomes: number
    correlation_adjusted_sample: number
    excluded_duplicate_outcomes: number
  }
  overdue_signal_ids: string[]
  fleet: {
    issue_count: number
    strikezone_issue_names: string[]
    other_issue_names: string[]
    unchanged_since: string | null
    checked_at: string | null
    last_alert_at: string | null
  } | null
  jobs: LabJob[]
  failing_jobs: number
  last_signal_at: string | null
  last_signal_age_minutes: number | null
  bridge_delivered_at: string | null
  bridge_age_minutes: number | null
  note: string
}
