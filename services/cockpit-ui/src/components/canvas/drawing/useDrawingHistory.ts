import { useEffect, useRef } from 'react'
import type { useCreateDrawing, useDeleteDrawing, useUpdateDrawing } from '../../../api/hooks/useDrawings'
import { UndoHistory, type UndoEntry } from './undo'

interface Mutations {
  create: ReturnType<typeof useCreateDrawing>
  update: ReturnType<typeof useUpdateDrawing>
  remove: ReturnType<typeof useDeleteDrawing>
}

/**
 * Undo for this session's drawing changes on one symbol.
 *
 * Reversing a change is itself a stored change: undoing a move records the
 * earlier position as a new version, and undoing a delete records the drawing
 * again. Nothing is erased from the server's history.
 */
export function useDrawingHistory(symbol: string, { create, update, remove }: Mutations) {
  const historyRef = useRef<UndoHistory | null>(null)
  if (!historyRef.current) historyRef.current = new UndoHistory()
  const history = historyRef.current

  useEffect(() => {
    history.clear()
  }, [history, symbol])

  const record = (entry: UndoEntry) => history.push(entry)

  const undo = (): boolean => {
    const entry = history.pop()
    if (!entry) return false
    if (entry.type === 'create') {
      remove.mutate({ symbol, drawingId: history.resolve(entry.id) })
    } else if (entry.type === 'update') {
      update.mutate({ drawingId: history.resolve(entry.id), input: entry.before })
    } else {
      for (const { id, input } of entry.drawings) {
        create
          .mutateAsync(input)
          .then((created) => history.alias(id, created.drawing_id))
          .catch(() => undefined) // shown from the mutation's error state
      }
    }
    return true
  }

  return { record, undo }
}
