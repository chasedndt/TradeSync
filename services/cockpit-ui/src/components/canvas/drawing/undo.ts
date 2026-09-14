import type { DrawingInput } from '../../../api/drawingTypes'

/** One change made on the canvas this session, recorded so it can be reversed. */
export type UndoEntry =
  | { type: 'create'; id: string }
  | { type: 'update'; id: string; before: DrawingInput }
  | { type: 'delete'; drawings: Array<{ id: string; input: DrawingInput }> }

const LIMIT = 50

/**
 * Session undo for drawings.
 *
 * A deleted drawing cannot be revived under its old id (its history is kept
 * server-side as deleted), so undoing a delete records it again under a new
 * id. Earlier entries still name the old id; `resolve` follows the chain so
 * undoing further back reaches the drawing that now stands in for it.
 */
export class UndoHistory {
  private entries: UndoEntry[] = []
  private readonly aliases = new Map<string, string>()

  get size(): number {
    return this.entries.length
  }

  push(entry: UndoEntry): void {
    this.entries.push(entry)
    if (this.entries.length > LIMIT) this.entries.shift()
  }

  pop(): UndoEntry | undefined {
    return this.entries.pop()
  }

  alias(previousId: string, currentId: string): void {
    if (previousId !== currentId) this.aliases.set(previousId, currentId)
  }

  resolve(id: string): string {
    let current = id
    const seen = new Set<string>()
    while (this.aliases.has(current) && !seen.has(current)) {
      seen.add(current)
      current = this.aliases.get(current)!
    }
    return current
  }

  clear(): void {
    this.entries = []
    this.aliases.clear()
  }
}
