/** Shapes of the paper risk routes in state-api (app/paper_risk_readmodel.py). Paper only. */

export type Refusal = { code: string; message: string }

export type ControlEvent = { created_at: string; entries_paused: boolean; reason: string; operator: string }
export type KillEvent = { created_at: string; action: 'kill' | 'resume' | 'close'; operator: string; reason: string; position_id: string | null }
export type PendingClose = { position_id: string; symbol: string; reason: string }

export type LimitValues = {
  daily_loss_limit_usdc: number
  max_drawdown_fraction: number
  max_gross_exposure_fraction: number
  max_symbol_exposure_fraction: number
  max_bucket_exposure_fraction: number
  correlation_threshold: number
  max_concurrent_positions: number
  max_entry_quote_age_s: number
  max_mark_age_s: number
}

type Share = { exposure_usdc: number; fraction_of_equity: number | null; limit: number; fraction_of_limit: number | null }

export type Utilisation = {
  daily_loss: { loss_usdc: number; limit_usdc: number; fraction_of_limit: number }
  drawdown: { fraction: number; limit: number; fraction_of_limit: number }
  gross_exposure: Share
  symbols: (Share & { symbol: string })[]
  buckets: (Share & { members: string[] })[]
  unmeasured_open_symbols: string[]
  positions: { open: number; limit: number }
  marks: { oldest_age_s: number | null; limit_s: number }
}

export type RiskState = {
  as_of: number
  entries_allowed: boolean
  entries_note: string
  blocking: Refusal[]
  pause: { entries_paused: boolean; reason: string; updated_at: string; recent: ControlEvent[] } | null
  kill_switch: { active: boolean; operator: string; reason: string; changed_at: string; pending_closes: PendingClose[]; recent: KillEvent[] } | null
  limits: { values: LimitValues; operator: string; reason: string; updated_at: string | null } | null
  account: { equity_usdc: number; cash_usdc: number; day_pnl_usdc: number; drawdown_fraction: number; peak_equity_usdc: number; gross_exposure_usdc: number } | null
  utilisation: Utilisation | null
  correlation: {
    measured_at: string | null; age_s: number; max_age_s: number; threshold: number | null; buckets: string[][]
    unmeasured: string[]; bar_interval: string; window_bars: number; source: string
  } | null
  reconciliation: { status: string; finished_at: string | null; mismatches: number; gaps: number } | null
  note: string
}

export type DailyPnl = { day: string; realised_usdc: number; unrealised_change_usdc: number; pnl_usdc: number; complete: boolean }

export type Account = {
  as_of: number
  starting_capital_usdc: number
  configured_starting_capital_usdc: number | null
  starting_capital_note: string | null
  cash_usdc: number
  realised: { net_usdc: number; gross_usdc: number; fees_usdc: number; funding_usdc: number; slippage_usdc: number; closed_positions: number; slippage_note: string }
  unrealised_usdc: number
  equity_usdc: number
  gross_exposure_usdc: number
  exposure_by_symbol: Record<string, number>
  oldest_mark_age_s: number | null
  peak_equity_usdc: number
  peak_equity_recorded_at: string | null
  drawdown_usdc: number
  drawdown_fraction: number
  day: { start: number; realised_usdc: number; unrealised_at_start_usdc: number; pnl_usdc: number }
  daily_pnl: DailyPnl[]
  note: string
}

export type Mismatch = { code: string; detail: string; position_id?: string }
export type Gap = { position_id: string; symbol: string; started_at: string; ended_at: string | null; seconds: number | null; ongoing: boolean }

export type Reconciliation = {
  last_run: {
    id: string; trigger: string; started_at: string | null; finished_at: string | null; status: 'clean' | 'mismatch' | 'failed'
    positions_checked: number; open_positions: number; mismatches: Mismatch[]; gaps: Gap[]; error: string | null
  } | null
  note: string
}

export type Audited = { operator: string; reason: string }
