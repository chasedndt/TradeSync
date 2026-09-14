import { useEffect } from 'react'
import type { ISeriesApi } from 'lightweight-charts'
import type { EvidenceMarker } from './chartTypes'

/** Paper-evidence markers on the candle series. */
export function useSeriesMarkers(series: ISeriesApi<'Candlestick'> | null, markers: EvidenceMarker[]) {
  useEffect(() => {
    if (!series) return
    series.setMarkers(
      markers.map((m) => {
        const change = m.kind !== 'continuation'
        const short = m.direction === 'SHORT'
        return {
          time: m.time as never,
          position: short ? 'aboveBar' : 'belowBar',
          color: short ? (change ? '#e0574a' : 'rgba(224,87,74,0.55)') : (change ? '#3fb27f' : 'rgba(63,178,127,0.55)'),
          shape: change ? (short ? 'arrowDown' : 'arrowUp') : 'circle',
          size: change ? 1 : 0.35,
          text: change ? m.label : '',
        }
      }),
    )
  }, [series, markers])
}
