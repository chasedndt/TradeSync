import { useEffect, useState } from 'react'
import type { ChartHandles } from '../chartTypes'
import { DrawingPrimitive } from './DrawingPrimitive'

/** The drawing layer, attached to the chart's candle series for as long as that chart exists. */
export function useDrawingPrimitive(handles: ChartHandles | null): DrawingPrimitive | null {
  const [layer, setLayer] = useState<DrawingPrimitive | null>(null)

  useEffect(() => {
    if (!handles) return
    const primitive = new DrawingPrimitive()
    handles.series.attachPrimitive(primitive)
    setLayer(primitive)
    return () => {
      setLayer(null)
      try {
        handles.series.detachPrimitive(primitive)
      } catch {
        // The chart was removed first, taking the layer with it.
      }
    }
  }, [handles])

  return layer
}
