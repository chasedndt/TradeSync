import type { Drawing, DrawingInput, DrawingList } from '../drawingTypes'

/** Local ids for drawings shown before the server has recorded them. */
const PENDING_PREFIX = 'pending:'
let pendingCount = 0

export function pendingDrawingId(): string {
  pendingCount += 1
  return `${PENDING_PREFIX}${pendingCount}`
}

export function isPendingDrawingId(id: string): boolean {
  return id.startsWith(PENDING_PREFIX)
}

/** The list with `drawing` added, or put in place of the drawing with its id. */
export function withDrawing(list: DrawingList | undefined, drawing: Drawing): DrawingList | undefined {
  if (!list) return list
  const index = list.drawings.findIndex((existing) => existing.drawing_id === drawing.drawing_id)
  const drawings = index === -1
    ? [...list.drawings, drawing]
    : list.drawings.map((existing, i) => (i === index ? drawing : existing))
  return { ...list, drawings }
}

export function withoutDrawing(list: DrawingList | undefined, drawingId: string): DrawingList | undefined {
  return list && { ...list, drawings: list.drawings.filter((existing) => existing.drawing_id !== drawingId) }
}

/** The list with one drawing edited as the server will record it: the next version. */
export function withEdit(list: DrawingList | undefined, drawingId: string, input: DrawingInput): DrawingList | undefined {
  const current = list?.drawings.find((existing) => existing.drawing_id === drawingId)
  return current ? withDrawing(list, { ...current, ...input, version: current.version + 1 }) : list
}
