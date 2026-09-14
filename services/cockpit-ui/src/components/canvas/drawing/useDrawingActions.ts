import { isPendingDrawingId } from '../../../api/hooks/drawingCache'
import {
  useClearDrawings,
  useCreateDrawing,
  useDeleteDrawing,
  useUpdateDrawing,
} from '../../../api/hooks/useDrawings'
import { drawingInput, isSavedShape, type SavedShape } from './shapes'
import type { Anchor, ChartShape, DrawingStyle, SavedKind } from './types'
import { useDrawingHistory } from './useDrawingHistory'

interface Options {
  symbol: string
  interval: string
  style: DrawingStyle
  shapes: readonly ChartShape[]
}

/**
 * Saving, moving, restyling and removing drawings, each recorded for undo.
 * Every change is a new stored version; nothing here overwrites history.
 */
export function useDrawingActions({ symbol, interval, style, shapes }: Options) {
  const create = useCreateDrawing()
  const update = useUpdateDrawing()
  const remove = useDeleteDrawing()
  const clear = useClearDrawings()
  const history = useDrawingHistory(symbol, { create, update, remove })

  const stored = (id: string): SavedShape | undefined => {
    const shape = shapes.find((candidate) => candidate.id === id)
    return shape && isSavedShape(shape) && !isPendingDrawingId(id) ? shape : undefined
  }
  const inputFor = (shape: SavedShape) => drawingInput(shape, symbol, interval)

  const save = (kind: SavedKind, anchors: Anchor[], label = '') => {
    create
      .mutateAsync(inputFor({ id: 'new', kind, anchors, style, label }))
      .then((created) => history.record({ type: 'create', id: created.drawing_id }))
      .catch(() => undefined) // shown from the mutation's error state
  }

  const edit = (id: string, changes: Partial<Pick<ChartShape, 'anchors' | 'style'>>) => {
    const shape = stored(id)
    if (!shape) return
    history.record({ type: 'update', id, before: inputFor(shape) })
    update.mutate({ drawingId: id, input: inputFor({ ...shape, ...changes }) })
  }

  const removeOne = (id: string) => {
    const shape = stored(id)
    if (!shape) return
    history.record({ type: 'delete', drawings: [{ id, input: inputFor(shape) }] })
    remove.mutate({ symbol, drawingId: id })
  }

  const removeAll = () => {
    const all = shapes.flatMap((shape) => stored(shape.id) ?? [])
    if (!all.length) return
    history.record({ type: 'delete', drawings: all.map((shape) => ({ id: shape.id, input: inputFor(shape) })) })
    clear.mutate(symbol)
  }

  return {
    save,
    edit,
    removeOne,
    removeAll,
    undo: history.undo,
    removing: remove.isPending || clear.isPending,
    saveFailed: create.isError || update.isError,
    removeFailed: remove.isError || clear.isError,
  }
}
