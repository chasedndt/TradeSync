import { useMemo, useRef, useState } from 'react'
import { isPendingDrawingId } from '../../../api/hooks/drawingCache'
import { useDrawings } from '../../../api/hooks/useDrawings'
import type { Candle } from '../../../api/types'
import type { ChartHandles } from '../chartTypes'
import { INTERVAL_SECONDS } from '../useCanvasLayers'
import type { InteractionHost } from './interaction/types'
import { shapeFromDrawing } from './shapes'
import type { Anchor, ChartShape, DrawingStyle, PixelPoint, ToolId } from './types'
import { useDrawingActions } from './useDrawingActions'
import { useDrawingInteraction } from './useDrawingInteraction'
import { useDrawingKeyboard } from './useDrawingKeyboard'
import { useDrawingPrefs } from './useDrawingPrefs'
import { useDrawingPrimitive } from './useDrawingPrimitive'
import { useDrawingScene } from './useDrawingScene'

export interface TextDraft {
  anchor: Anchor
  at: PixelPoint
}

interface Options {
  handles: ChartHandles | null
  symbol: string
  interval: string
  candles: readonly Candle[]
}

const MAX_TEXT = 280
const NO_SHAPES: ChartShape[] = []

/** The drawing layer for one symbol: the rail's tool, the selection, the text being typed, and edits. */
export function useDrawingController({ handles, symbol, interval, candles }: Options) {
  const { data } = useDrawings(symbol)
  const prefs = useDrawingPrefs()
  const [tool, setTool] = useState<ToolId>('cursor')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [textDraft, setTextDraft] = useState<TextDraft | null>(null)

  const shapes = useMemo(() => data?.drawings.map(shapeFromDrawing) ?? NO_SHAPES, [data])
  const selected = shapes.find((shape) => shape.id === selectedId) ?? null
  const axis = useMemo(
    () => ({ times: candles.map((candle) => candle.time), step: INTERVAL_SECONDS[interval] ?? 900 }),
    [candles, interval],
  )
  const actions = useDrawingActions({ symbol, interval, style: prefs.style, shapes })

  const layer = useDrawingPrimitive(handles)
  useDrawingScene(layer, { axis, shapes, selectedId: selected?.id ?? null, hidden: prefs.hidden })

  const current = { tool, style: prefs.style, selectedId, hidden: prefs.hidden, locked: prefs.locked }
  const stateRef = useRef(current)
  stateRef.current = current

  const host: InteractionHost = {
    state: () => stateRef.current,
    shape: (id) => (isPendingDrawingId(id) ? undefined : shapes.find((shape) => shape.id === id)),
    select: setSelectedId,
    create: (kind, anchors) => actions.save(kind, anchors),
    move: (id, anchors) => actions.edit(id, { anchors }),
    placed: () => setTool('cursor'),
    requestText: (anchor, at) => setTextDraft({ anchor, at }),
  }
  const interaction = useDrawingInteraction(handles, layer, host, tool, prefs.locked)

  const deleteSelected = (): boolean => {
    if (!selected || prefs.locked) return false
    actions.removeOne(selected.id)
    setSelectedId(null)
    return true
  }

  const escape = (): boolean => {
    if (textDraft || tool !== 'cursor') {
      interaction?.cancel()
      setTextDraft(null)
      setTool('cursor')
      return true
    }
    if (interaction?.cancel()) return true
    if (!selectedId) return false
    setSelectedId(null)
    return true
  }

  useDrawingKeyboard({ escape, deleteSelected, undo: actions.undo }, handles !== null)

  return {
    tool,
    chooseTool: (next: ToolId) => {
      setTextDraft(null)
      if (next !== 'cursor') {
        setSelectedId(null)
        if (prefs.hidden) prefs.change({ hidden: false })
      }
      setTool((active) => (active === next ? 'cursor' : next))
    },
    shapes,
    selected,
    select: (id: string) => {
      setTool('cursor')
      setSelectedId(id)
    },
    style: prefs.style,
    restyle: (style: DrawingStyle) => {
      prefs.change({ style })
      if (selected && !prefs.locked) actions.edit(selected.id, { style })
    },
    hidden: prefs.hidden,
    toggleHidden: () => {
      prefs.change({ hidden: !prefs.hidden })
      setSelectedId(null)
      setTool('cursor')
    },
    locked: prefs.locked,
    toggleLocked: () => prefs.change({ locked: !prefs.locked }),
    deleteSelected,
    removeDrawing: (id: string) => {
      if (prefs.locked) return
      actions.removeOne(id)
      if (id === selectedId) setSelectedId(null)
    },
    clearAll: () => {
      actions.removeAll()
      setSelectedId(null)
    },
    textDraft,
    submitText: (text: string) => {
      const label = text.trim().slice(0, MAX_TEXT)
      if (textDraft && label) actions.save('text', [textDraft.anchor], label)
      setTextDraft(null)
      setTool('cursor')
    },
    cancelText: () => {
      setTextDraft(null)
      setTool('cursor')
    },
    removing: actions.removing,
    saveFailed: actions.saveFailed,
    removeFailed: actions.removeFailed,
  }
}
