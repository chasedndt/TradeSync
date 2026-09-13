import type { HermesBriefing, MarketOutlook } from '../../api/types'

export function hasOutlook(o: unknown): o is MarketOutlook {
  return typeof o === 'object' && o !== null && 'breadth' in o && 'key_events' in o
}

export function hasBriefing(b: unknown): b is HermesBriefing {
  return typeof b === 'object' && b !== null && 'status' in b
}
