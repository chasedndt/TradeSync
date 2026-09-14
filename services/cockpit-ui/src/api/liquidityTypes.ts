/** Liquidity and liquidation payloads from the state API: resting books, estimated liquidation levels and received liquidations. */

export type HeatmapWindow = '6h' | '24h' | '3d' | '7d' | '30d'
export type MapWindow = '24h' | '3d' | '7d' | '30d'
export type ReceivedWindow = '1h' | '24h' | '7d'

export interface Wall {
  price: number
  usd: number
  distance_bps: number
}

export interface LiquidityHeatmap {
  symbol: string
  window: HeatmapWindow
  n_sig_figs: number
  bucket_seconds: number
  times: number[]
  prices: number[]
  price_step: number | null
  bids: [number, number, number][]
  asks: [number, number, number][]
  mid: [number, number][]
  books_per_bucket: number[]
  max_usd: number
  p95_usd: number
  latest: {
    observed_at: string
    mid: number
    bids: [number, number][]
    asks: [number, number][]
    walls: { below: Wall | null; above: Wall | null; bid_usd: number; ask_usd: number; imbalance: number | null; within_pct: number }
  } | null
  recording_since: string | null
  note: string
}

export interface Cluster {
  price: number
  usd: number
  distance_pct: number
}

export interface LiquidationMap {
  symbol: string
  window: MapWindow
  interval: string
  bucket_seconds: number
  times: number[]
  prices: number[]
  cells: [number, number, number, number][]
  max_usd: number
  profile: { price: number; long: [number, number][]; short: [number, number][] }
  clusters: { above: Cluster[]; below: Cluster[] }
  assumptions: { leverage: Record<string, number>; maintenance_margin: number }
  skew_3pct: number | null
  coverage: { from: string; to: string; bars: number }
  note: string
}

export interface ReceivedLiquidations {
  symbol: string
  window: ReceivedWindow
  bucket_seconds: number
  totals: { long: number; short: number }
  by_source: Record<string, { long: number; short: number }>
  buckets: [number, number, number][]
  largest: { source: string; side: 'long' | 'short'; price: number; usd: number; time: string }[]
  events: number
  recording_since: string | null
  note: string
}

export interface WindowCandle {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}
