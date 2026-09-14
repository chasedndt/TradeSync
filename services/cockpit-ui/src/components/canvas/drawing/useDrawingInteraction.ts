import { useEffect, useRef, useState } from 'react'
import type { ChartHandles } from '../chartTypes'
import type { DrawingPrimitive } from './DrawingPrimitive'
import { DrawingInteraction } from './interaction/DrawingInteraction'
import type { InteractionHost } from './interaction/types'
import type { ToolId } from './types'

/**
 * Pointer handling on the chart, created once per chart. The host is read
 * through a ref, so every event sees the page as it is now.
 */
export function useDrawingInteraction(
  handles: ChartHandles | null,
  layer: DrawingPrimitive | null,
  host: InteractionHost,
  tool: ToolId,
  locked: boolean,
): DrawingInteraction | null {
  const hostRef = useRef(host)
  hostRef.current = host
  const [interaction, setInteraction] = useState<DrawingInteraction | null>(null)

  useEffect(() => {
    if (!handles || !layer) return
    const created = new DrawingInteraction(handles.chart, layer, {
      state: () => hostRef.current.state(),
      shape: (id) => hostRef.current.shape(id),
      select: (id) => hostRef.current.select(id),
      create: (kind, anchors) => hostRef.current.create(kind, anchors),
      move: (id, anchors) => hostRef.current.move(id, anchors),
      placed: () => hostRef.current.placed(),
      requestText: (anchor, at) => hostRef.current.requestText(anchor, at),
    })
    setInteraction(created)
    return () => {
      created.dispose()
      setInteraction(null)
    }
  }, [handles, layer])

  useEffect(() => {
    interaction?.setTool(tool, locked)
  }, [interaction, tool, locked])

  return interaction
}
