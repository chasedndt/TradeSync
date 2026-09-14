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
