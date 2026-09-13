/** The timeframe outlook as the state API serves it: records of what followed, not forecasts. */

export type HorizonKey = '3d' | '1w' | '2w' | '1m' | '3m' | '6m'
export type BandKey = 'lower' | 'medium' | 'higher'
export type RecordLean = 'up' | 'down' | 'mixed' | 'too_few' | 'unavailable'

export interface RecordStats {
  days: number
  independent_windows: number
  share_up: number | null
  median_pct: number | null
  median_abs_pct: number | null
  p10_pct: number | null
  p25_pct: number | null
  p75_pct: number | null
  p90_pct: number | null
}

export interface HorizonRead {
  key: HorizonKey
  label: string
  days: number
  band: BandKey
  available: boolean
  reason?: string
  trend?: { state: string; ma_days: number; ma: number; ma_slope_pct: number | null; distance_pct: number | null }
  momentum?: { state: 'up' | 'down'; change_pct: number }
  record?: { same_state: RecordStats; same_trend: RecordStats; all_history: RecordStats }
  lean?: RecordLean
  lean_basis?: 'same_state' | 'same_trend'
  implied_range?: { sigma_pct: number; low: number; high: number } | null
  levels?: { trend_flips_at: number; recent_high: number; recent_low: number; recent_days: number }
}

export interface HorizonOutlook {
  schema_version: 'horizon_outlook_v1'
  symbol: string
  generated_at: string
  available: boolean
  reason?: string
  last_close?: number
  history?: { days: number; from: string; to: string }
  horizons?: HorizonRead[]
  bands?: { band: BandKey; label: string; horizons: HorizonKey[]; leans: Record<string, string>; agreement: string }[]
  method?: Record<string, string>
}

export interface FeatureEvaluation {
  key: string
  label: string
  kind: 'directional' | 'context'
  measures: string
  state: string | null
  lean: string
  value: number | null
  text: string
  record: RecordStats
  record_lean: RecordLean
}

export interface HorizonEvaluation {
  horizon: HorizonKey
  features: FeatureEvaluation[]
  record_tally: Record<RecordLean, number>
  summary: string
}

export interface HorizonReading {
  status: 'none' | 'running' | 'ok' | 'refused' | 'unavailable' | 'not_configured'
  content?: string
  model?: string | null
  detail?: string
  elapsed_ms?: number
  started_at?: string
  finished_at?: string
}

export interface HorizonFeatureInfo {
  key: string
  label: string
  kind: 'directional' | 'context'
  measures: string
}

export interface HorizonPage {
  schema_version: 'horizon_page_v1'
  symbol: string
  computed_at: string
  bands: Record<BandKey, string>
  horizons: { key: HorizonKey; label: string; days: number; band: BandKey }[]
  features: HorizonFeatureInfo[]
  outlook: HorizonOutlook
  evaluation: Partial<Record<HorizonKey, HorizonEvaluation>>
  reading: HorizonReading
  history_note: string
  note: string
}

export interface ChartSeries {
  kind: 'line' | 'histogram'
  label: string
  role: string
  pane: 'price' | 'lower'
  points: [number, number][]
  guides?: number[]
  range?: [number, number]
}

export interface ConeLine {
  quantile: 'p10_pct' | 'p25_pct' | 'median_pct' | 'p75_pct' | 'p90_pct'
  label: string
  points: [number, number][]
}

export interface HorizonChartPayload {
  horizon: HorizonKey
  candles: { time: number; open: number; high: number; low: number; close: number; volume: number }[]
  overlays: Record<string, ChartSeries[]>
  projection: { basis: string; days?: number; independent_windows?: number; end_time?: number; lines: ConeLine[]; note?: string }
}
