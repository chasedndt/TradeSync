import { useEffect } from 'react'
import type { TimeAxis } from './anchors'
import type { DrawingPrimitive } from './DrawingPrimitive'
import type { ChartShape } from './types'

interface Scene {
  axis: TimeAxis
  shapes: readonly ChartShape[]
  selectedId: string | null
  hidden: boolean
}

/** Keeps the drawing layer in step with the page: the bars, the stored shapes, the selection. */
export function useDrawingScene(layer: DrawingPrimitive | null, { axis, shapes, selectedId, hidden }: Scene): void {
  useEffect(() => {
    layer?.setAxis(axis)
  }, [layer, axis])

  useEffect(() => {
    layer?.setShapes(shapes)
  }, [layer, shapes])

  useEffect(() => {
    layer?.setSelection(selectedId)
  }, [layer, selectedId])

  useEffect(() => {
    layer?.setHidden(hidden)
  }, [layer, hidden])
}
