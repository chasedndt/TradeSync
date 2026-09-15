import { useEffect, useId, useRef, useState } from 'react'
import styles from './ConfirmDialog.module.css'

interface Props {
  title: string
  body: string
  confirmLabel: string
  /** When set, the confirm button stays disabled until this word is typed. */
  phrase?: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/** Asks before a paper risk change. Focus starts on Cancel, so a stray Enter changes nothing. */
export function ConfirmDialog({ title, body, confirmLabel, phrase, danger, busy, onConfirm, onCancel }: Props) {
  const cancelRef = useRef<HTMLButtonElement | null>(null)
  const [typed, setTyped] = useState('')
  const titleId = useId()
  const bodyId = useId()
  const ready = !phrase || typed.trim().toUpperCase() === phrase

  useEffect(() => {
    cancelRef.current?.focus()
  }, [])

  return (
    <div
      className={styles.backdrop}
      onKeyDown={(event) => {
        if (event.key !== 'Escape') return
        event.stopPropagation()
        onCancel()
      }}
    >
      <div className={styles.dialog} role="alertdialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={bodyId}>
        <h4 id={titleId}>{title}</h4>
        <p id={bodyId}>{body}</p>
        {phrase && (
          <label className={styles.phrase}>
            Type {phrase} to confirm
            <input value={typed} onChange={(event) => setTyped(event.target.value)} autoComplete="off" spellCheck={false} />
          </label>
        )}
        <div className={styles.actions}>
          <button ref={cancelRef} type="button" className="chip" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className={`chip ${danger ? styles.danger : ''}`} disabled={!ready || busy} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
