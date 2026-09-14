import { useMemo } from 'react'
import type { DepthResponse, Opportunity } from '../../api/types'
import type { Drawing } from '../../api/drawingTypes'
import type { Shape } from './DrawingOverlay'
import type { EvidenceMarker, PriceLevel } from './chartTypes'

/** Candle duration in seconds, used to snap a signal time to its candle open. */
export const INTERVAL_SECONDS: Record<string, number> = {
  '1m': 60,
  '5m': 300,
  '15m': 900,
  '1h': 3600,
  '4h': 14400,
  '1d': 86400,
}

/**
 * Recorded paper opportunities as chart markers.
 *
 * The producer records a verdict every 60s, so on anything slower than 1m many
 * opportunities land inside one candle. Stacking them all makes the chart
 * unreadable, so each candle carries one marker that says how many it stands
 * for — the count is shown rather than the others being silently dropped.
 */
export function useEvidenceMarkers(
  opportunities: Opportunity[] | undefined,
  symbol: string,
  interval: string,
  mode: 'changes' | 'all' = 'changes',
): EvidenceMarker[] {
  return useMemo(() => {
    if (!opportunities) return []
    const bucket = INTERVAL_SECONDS[interval] ?? 900

    const perCandle = new Map<number, { latest: Opportunity; count: number }>()
    for (const o of opportunities) {
      if (o.symbol !== symbol) continue
      const seconds = Math.floor(new Date(o.snapshot_ts).getTime() / 1000)
      // Snap to the candle open, otherwise the library drops the marker.
      const slot = Math.floor(seconds / bucket) * bucket
      const existing = perCandle.get(slot)
      if (!existing) {
        perCandle.set(slot, { latest: o, count: 1 })
      } else {
        existing.count += 1
        if (new Date(o.snapshot_ts) > new Date(existing.latest.snapshot_ts)) {
          existing.latest = o
        }
      }
    }

    // One call per candle is still a wall of labels when a side is held for
    // hours. Only a change of side is labelled; a held side is a small dot,
    // and in "changes" mode it is not drawn at all.
    const ordered = Array.from(perCandle.entries()).sort((a, b) => a[0] - b[0])
    const out: EvidenceMarker[] = []
    let previous: 'LONG' | 'SHORT' | null = null
    for (const [time, { latest, count }] of ordered) {
      const direction = (latest.dir === 'SHORT' ? 'SHORT' : 'LONG') as 'LONG' | 'SHORT'
      const change = direction !== previous
      previous = direction
      if (!change && mode === 'changes') continue
      out.push({
        time,
        direction,
        kind: change ? 'change' : 'continuation',
        label: change ? `${direction}${count > 1 ? ` ×${count}` : ''}` : '',
      })
    }
    return out
  }, [opportunities, symbol, interval, mode])
}

/**
 * Horizontal price lines: the operator's own levels, plus any resting walls.
 *
 * The two are kept visually distinct. An operator level is dashed and stays
 * until they remove it; a wall is dotted and derived from the current book,
 * where the size can be pulled the moment it is approached.
 */
export function usePriceLevels(
  drawings: Drawing[] | undefined,
  depth: DepthResponse | undefined,
  showDepth: boolean,
): { levels: PriceLevel[]; annotations: PriceLevel[] } {
  return useMemo(() => {
    const annotations = (drawings ?? [])
      .filter((d) => d.kind === 'horizontal' && d.points.length)
      .map((d) => ({
        drawingId: d.drawing_id,
        price: d.points[0].price,
        // The version is shown because an edit supersedes rather than
        // overwrites, so "v3" means this level has been revised twice.
        label: d.label ? `${d.label} · v${d.version}` : `v${d.version}`,
        colour: d.colour || undefined,
        style: 'dashed' as const,
      }))

    const walls =
      showDepth && depth
        ? depth.walls.map((wall) => ({
            drawingId: `wall:${wall.side}:${wall.price}`,
            price: wall.price,
            label: `${wall.side} wall ${(wall.share_of_side * 100).toFixed(0)}%`,
            colour: wall.side === 'bid' ? '#3fb27f' : '#e0574a',
            style: 'dotted' as const,
          }))
        : []

    return { levels: [...annotations, ...walls], annotations }
  }, [drawings, depth, showDepth])
}

/** Two-anchor operator shapes, drawn in the overlay above the chart. */
export function useShapes(drawings: Drawing[] | undefined): Shape[] {
  return useMemo(
    () =>
      (drawings ?? [])
        .filter((d) => (d.kind === 'trendline' || d.kind === 'range') && d.points.length === 2)
        .map((d) => ({
          drawingId: d.drawing_id,
          kind: d.kind as 'trendline' | 'range',
          points: d.points,
          label: d.label ? `${d.label} · v${d.version}` : `v${d.version}`,
          colour: d.colour || undefined,
        })),
    [drawings],
  )
}
