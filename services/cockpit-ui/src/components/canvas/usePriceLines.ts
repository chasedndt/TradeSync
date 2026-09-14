import { useEffect, useRef } from 'react'
import { LineStyle, type IPriceLine, type ISeriesApi } from 'lightweight-charts'
import type { PriceLevel } from './chartTypes'

/** Horizontal price lines on the candle series, kept in step with `levels`. */
export function usePriceLines(series: ISeriesApi<'Candlestick'> | null, levels: PriceLevel[]) {
  const priceLinesRef = useRef<Map<string, IPriceLine>>(new Map())

  // Lines belong to one series; a removed chart takes its lines with it.
  useEffect(() => {
    priceLinesRef.current.clear()
  }, [series])

  useEffect(() => {
    if (!series) return
    const existing = priceLinesRef.current
    const wanted = new Set(levels.map((l) => l.drawingId))

    // Remove lines whose drawing is gone, so a deleted level leaves the chart.
    for (const [id, line] of existing) {
      if (!wanted.has(id)) {
        series.removePriceLine(line)
        existing.delete(id)
      }
    }
    // Recreate changed ones: the library has no update for a price line.
    for (const level of levels) {
      const previous = existing.get(level.drawingId)
      if (previous) series.removePriceLine(previous)
      existing.set(
        level.drawingId,
        series.createPriceLine({
          price: level.price,
          color: level.colour || '#e3b23c',
          lineWidth: 1,
          lineStyle: level.style === 'dotted' ? LineStyle.Dotted : LineStyle.Dashed,
          axisLabelVisible: true,
          title: level.label || '',
        }),
      )
    }
  }, [series, levels])
}
