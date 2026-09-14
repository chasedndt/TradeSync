/** The timeframe outlook as the state API serves it: records of what followed and earned weights, not forecasts. */

export type HorizonKey = '1h' | '4h' | '8h' | '1d' | '3d' | '1w' | '2w' | '1m' | '3m' | '6m'
export type BandKey = 'short' | 'lower' | 'medium' | 'higher'
export type Interval = '15m' | '1h' | '1d'
export type PartKey = 'short' | 'long'
export type RecordLean = 'up' | 'down' | 'mixed' | 'too_few' | 'unavailable'
export type CombinedLean = 'up' | 'down' | 'balanced' | 'unweighted'
export type ReadingStatus = 'none' | 'running' | 'ok' | 'refused' | 'unavailable' | 'not_configured'

export const HORIZON_KEYS: HorizonKey[] = ['1h', '4h', '8h', '1d', '3d', '1w', '2w', '1m', '3m', '6m']
/** Short-term horizons are measured from 15-minute and hourly candles, the rest from daily candles. */
export const partOf = (interval: Interval): PartKey => (interval === '1d' ? 'long' : 'short')

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
  steps: number
  interval: Interval
  band: BandKey
  available: boolean
  reason?: string
  trend?: { state: string; ma_bars: number; ma_label: string; ma: number; ma_slope_pct: number | null; distance_pct: number | null }
  momentum?: { state: 'up' | 'down'; change_pct: number }
  record?: { same_state: RecordStats; same_trend: RecordStats; all_history: RecordStats }
  lean?: RecordLean
  lean_basis?: 'same_state' | 'same_trend'
  implied_range?: { sigma_pct: number; low: number; high: number } | null
  levels?: { trend_flips_at: number; recent_high: number; recent_low: number; recent_bars: number; recent_label: string }
}

export interface HorizonOutlook {
  schema_version: 'horizon_outlook_v2'
  symbol: string
  available: boolean
  reason?: string | null
  last_close?: number | null
  history: Partial<Record<Interval, { bars: number; from: string; to: string; last_bar_complete: boolean }>>
  horizons: HorizonRead[]
  bands: { band: BandKey; label: string; horizons: HorizonKey[]; leans: Record<string, string>; agreement: string }[]
  method: Record<string, string>
}

export interface HeldOut {
  status: 'measured' | 'too_few_test_windows' | 'no_leaning_state' | 'too_little_history'
  learned_windows: number
  test_windows: number
  hit_rate: number | null
  chance: number | null
  skill: number | null
  z: number | null
  edge_pct: number | null
  weight: number
  leaning_states: Record<string, 'up' | 'down'>
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
  held_out: HeldOut
  weight: number
  current_lean: -1 | 0 | 1
  contribution: number
}

export interface CombinedReading {
  score: number | null
  lean: CombinedLean
  total_weight: number
  earned: string[]
  sentence: string
}

export interface HorizonEvaluation {
  horizon: HorizonKey
  features: FeatureEvaluation[]
  record_tally: Record<RecordLean, number>
  summary: string
  base_share_up: number | null
  combined: CombinedReading
}

export interface BandReading {
  status: ReadingStatus
  attempt?: { status: ReadingStatus; started_at: string | null; finished_at: string | null; detail?: string | null }
  content?: string
  model?: string | null
  measured_at?: string
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
  schema_version: 'horizon_page_v2'
  symbol: string
  computed_at: Partial<Record<PartKey, string>>
  bands: Record<BandKey, string>
  horizons: { key: HorizonKey; label: string; steps: number; interval: Interval; band: BandKey }[]
  features: HorizonFeatureInfo[]
  outlook: HorizonOutlook
  evaluation: Partial<Record<HorizonKey, HorizonEvaluation>>
  readings: Record<BandKey, BandReading>
  errors: Partial<Record<PartKey, string>>
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
  interval: Interval
  candles: { time: number; open: number; high: number; low: number; close: number; volume: number }[]
  overlays: Record<string, ChartSeries[]>
  projection: { basis: string; windows?: number; independent_windows?: number; end_time?: number; lines: ConeLine[]; note?: string }
}
