import { useEffect, useRef, useState } from 'react'
import type { PixelPoint } from './types'
import styles from './TextInput.module.css'

const MAX_LENGTH = 280

interface Props {
  /** The clicked point in the pane; the text sits above and to the right of it. */
  at: PixelPoint
  colour: string
  onSubmit: (text: string) => void
  onCancel: () => void
}

/** Inline entry for a text drawing: Enter saves, Esc cancels, clicking away cancels. */
export function TextInput({ at, colour, onSubmit, onCancel }: Props) {
  const [value, setValue] = useState('')
  const inputRef = useRef<HTMLInputElement | null>(null)
  // Saving or cancelling unmounts the input, and that blur must not cancel a save.
  const doneRef = useRef(false)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const finish = (save: boolean) => {
    if (doneRef.current) return
    doneRef.current = true
    if (save) onSubmit(value)
    else onCancel()
  }

  return (
    <input
      ref={inputRef}
      className={styles.input}
      style={{ left: at.x, top: at.y, borderColor: colour }}
      value={value}
      maxLength={MAX_LENGTH}
      placeholder="Text, then Enter"
      aria-label="Drawing text"
      onChange={(event) => setValue(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.preventDefault()
          finish(true)
        } else if (event.key === 'Escape') {
          event.preventDefault()
          event.stopPropagation()
          finish(false)
        }
      }}
      onBlur={() => finish(false)}
    />
  )
}
