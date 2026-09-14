export interface EvidenceMarker {
  /** UNIX seconds, aligned to a candle open. */
  time: number
  direction: 'LONG' | 'SHORT' | 'NONE'
  label: string
  /** A change of side is drawn as a labelled arrow; a held side as a small unlabelled dot. */
  kind?: 'change' | 'continuation'
}

export interface PriceLevel {
  drawingId: string
  price: number
  label: string
  colour?: string
  /**
   * Dashed is an operator annotation; dotted is derived from venue data and is
   * not something the operator drew. Keeping them visually distinct matters —
   * a resting wall disappears the moment the order is pulled, while a level the
   * operator placed is theirs until they remove it.
   */
  style?: 'dashed' | 'dotted'
}
