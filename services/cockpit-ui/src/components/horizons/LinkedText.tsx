import { useMemo } from 'react'
import styles from './LinkedText.module.css'

export interface LinkTarget {
  label: string
  key: string
}

interface Part {
  text: string
  key?: string
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

function split(text: string, targets: LinkTarget[]): Part[] {
  if (!targets.length || !text) return [{ text }]
  const ordered = [...targets].sort((a, b) => b.label.length - a.label.length)
  const byName = new Map(ordered.map((t) => [t.label.toLowerCase(), t.key]))
  const pattern = new RegExp(`\\b(${ordered.map((t) => escape(t.label)).join('|')})\\b`, 'gi')
  const parts: Part[] = []
  let last = 0
  let match: RegExpExecArray | null
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) parts.push({ text: text.slice(last, match.index) })
    parts.push({ text: match[0], key: byName.get(match[0].toLowerCase()) })
    last = match.index + match[0].length
  }
  if (last < text.length) parts.push({ text: text.slice(last) })
  return parts
}

/**
 * Text in which every feature name is a link to that feature's chart. Used for
 * the page's own sentences and for Hermes's prose alike, so a name read anywhere
 * takes the reader to what it describes.
 */
export function LinkedText({ text, targets, onPick }: { text: string; targets: LinkTarget[]; onPick: (key: string) => void }) {
  const parts = useMemo(() => split(text, targets), [text, targets])
  return (
    <>
      {parts.map((part, i) =>
        part.key ? (
          <button key={i} type="button" className={styles.link} onClick={() => onPick(part.key as string)} title="Show this feature's chart">
            {part.text}
          </button>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </>
  )
}
