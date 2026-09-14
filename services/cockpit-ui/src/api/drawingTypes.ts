export interface DrawingPoint {
  /** UNIX seconds, matching the chart. */
  time_s: number
  price: number
}

export type DrawingKind =
  | 'horizontal'
  | 'trendline'
  | 'range'
  | 'note'
  | 'ray'
  | 'extended_line'
  | 'horizontal_ray'
  | 'vertical'
  | 'rectangle'
  | 'fib_retracement'
  | 'pencil'
  | 'text'

/** How a drawing is drawn: colour #rrggbb, width 1-4, dashed. Presentation only. */
export interface DrawingStyle {
  colour: string
  width: number
  dashed: boolean
}

export interface DrawingInput {
  symbol: string
  interval: string
  kind: DrawingKind
  points: DrawingPoint[]
  label?: string
  /** Free-form colour from before styles existed; new drawings carry `style`. */
  colour?: string
  /** Null on versions stored before styles existed. */
  style?: DrawingStyle | null
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
  /** The interval asked for; null when every interval was read. */
  interval: string | null
  /** True when the list holds the symbol's drawings from every interval. */
  all_intervals?: boolean
  authority: string
  drawings: Drawing[]
}
