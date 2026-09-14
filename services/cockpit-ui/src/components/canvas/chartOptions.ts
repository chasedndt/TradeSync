import { ColorType } from 'lightweight-charts'

export function priceChartOptions(height: number) {
  return {
    height,
    layout: {
      background: { type: ColorType.Solid, color: 'transparent' },
      textColor: '#8397aa',
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
    },
    grid: {
      vertLines: { color: 'rgba(131,151,170,0.10)' },
      horzLines: { color: 'rgba(131,151,170,0.10)' },
    },
    // Pinned width shared with the context panes below, so their plot areas
    // start at the same x and a funding spike lines up with its candle.
    rightPriceScale: { borderColor: 'rgba(131,151,170,0.25)', minimumWidth: 100 },
    timeScale: { borderColor: 'rgba(131,151,170,0.25)', timeVisible: true },
    crosshair: { mode: 0 },
  } as const
}

export const CANDLE_SERIES_OPTIONS = {
  upColor: '#3fb27f',
  downColor: '#e0574a',
  borderUpColor: '#3fb27f',
  borderDownColor: '#e0574a',
  wickUpColor: '#3fb27f',
  wickDownColor: '#e0574a',
} as const

export const VOLUME_SERIES_OPTIONS = {
  priceFormat: { type: 'volume' },
  priceScaleId: 'volume',
  color: 'rgba(131,151,170,0.35)',
} as const

export const VOLUME_SCALE_MARGINS = { top: 0.82, bottom: 0 } as const
