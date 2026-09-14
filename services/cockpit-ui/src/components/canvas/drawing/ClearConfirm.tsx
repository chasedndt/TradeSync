import { useEffect, useRef } from 'react'
import styles from './ClearConfirm.module.css'

interface Props {
  symbol: string
  count: number
  onConfirm: () => void
  onCancel: () => void
}

/** Asks before removing every drawing for a symbol. Each keeps its stored history either way. */
export function ClearConfirm({ symbol, count, onConfirm, onCancel }: Props) {
  const cancelRef = useRef<HTMLButtonElement | null>(null)

  // Focus lands on Cancel, so a stray Enter does not delete anything.
  useEffect(() => {
    cancelRef.current?.focus()
  }, [])

  return (
    <div
      className={styles.popover}
      role="alertdialog"
      aria-label={`Delete all drawings for ${symbol}`}
      onKeyDown={(event) => {
        if (event.key !== 'Escape') return
        event.stopPropagation()
        onCancel()
      }}
    >
      <p>
        Delete all {count} drawing{count === 1 ? '' : 's'} for {symbol.replace('-PERP', '')}, on every interval?
      </p>
      <p className={styles.note}>Each keeps its stored history. Ctrl+Z brings them back during this visit.</p>
      <div className={styles.actions}>
        <button ref={cancelRef} type="button" className="chip" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className={`chip ${styles.danger}`} onClick={onConfirm}>
          Delete all
        </button>
      </div>
    </div>
  )
}
