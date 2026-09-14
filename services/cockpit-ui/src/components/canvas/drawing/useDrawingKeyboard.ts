import { useEffect, useRef } from 'react'

/** Each returns whether it did something, so a key that does nothing keeps its usual meaning. */
interface Keys {
  escape(): boolean
  deleteSelected(): boolean
  undo(): boolean
}

function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
}

/** Esc, Delete or Backspace, and Ctrl+Z (Cmd+Z) while the canvas is open, except when typing. */
export function useDrawingKeyboard(keys: Keys, enabled: boolean): void {
  const keysRef = useRef(keys)
  keysRef.current = keys

  useEffect(() => {
    if (!enabled) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || isTyping(event.target)) return
      const current = keysRef.current
      let handled = false
      if (event.key === 'Escape') handled = current.escape()
      else if (event.key === 'Delete' || event.key === 'Backspace') handled = current.deleteSelected()
      else if ((event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey && event.key.toLowerCase() === 'z') {
        handled = current.undo()
      }
      if (handled) event.preventDefault()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [enabled])
}
