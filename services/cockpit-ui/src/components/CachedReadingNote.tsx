import type { CacheState } from '../api/outcomeEvidenceTypes'
import { since } from './ledger/format'
import styles from './CachedReadingNote.module.css'

/** When a slow reading was measured, whether it is being measured again, and the last refresh error. */
export function CachedReadingNote({ computedAt, cache }: { computedAt: string; cache: CacheState }) {
  const flags = [
    cache.refreshing ? 'being measured again' : null,
    cache.stale ? `older than its ${Math.round(cache.ttl_s / 60)}-minute lifetime` : null,
  ].filter(Boolean)
  return (
    <span className={styles.note}>
      measured {since(computedAt)} ({new Date(computedAt).toISOString().slice(11, 19)} UTC)
      {flags.length > 0 && ` · ${flags.join(' · ')}`}
      {cache.last_error && <span className={styles.warn}> · last refresh failed: {cache.last_error}</span>}
    </span>
  )
}
