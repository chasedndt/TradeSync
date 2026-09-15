import type { EvidenceItem, EvidenceRecord } from './paperTypes'
import { age, exactTime, price, words } from './paperFormat'
import styles from './PaperEvidenceItem.module.css'

const SHOWN = 12
const TIMES = new Set(['observed_at', 'received_at', 'age_s', 'id'])

type Wall = { price?: number; usd?: number; distance_bps?: number; side?: string; notional_usd?: number; share_of_side?: number }

const walls = (value: unknown): string | null => {
  if (Array.isArray(value)) {
    return value.length === 0
      ? 'no level holds 15% of its side'
      : (value as Wall[]).map((w) => `${w.side} wall ${price(w.price)} (${price(w.notional_usd)} USD, ${Math.round((w.share_of_side ?? 0) * 100)}% of its side)`).join('; ')
  }
  if (value && typeof value === 'object') {
    const w = value as { below?: Wall | null; above?: Wall | null; imbalance?: number | null; within_pct?: number }
    const side = (label: string, x?: Wall | null) => (x ? `${label} ${price(x.price)} (${price(x.usd)} USD, ${x.distance_bps} bps away)` : `no ${label}`)
    return `${side('largest bid below', w.below)}; ${side('largest ask above', w.above)}; balance ${w.imbalance ?? '—'} within ${w.within_pct}%`
  }
  return null
}

const detail = (record: EvidenceRecord): string => {
  const parts: string[] = []
  const wallText = walls(record.walls)
  if (wallText) parts.push(wallText)
  if (Array.isArray(record.horizons)) parts.push((record.horizons as { key?: string; lean?: string }[]).map((h) => `${h.key} ${words(h.lean)}`).join(', '))
  if (Array.isArray(record.contributing_features)) parts.push(`${record.contributing_features.length} contributing features`)
  for (const [key, value] of Object.entries(record)) {
    if (TIMES.has(key) || value == null || typeof value === 'object') continue
    parts.push(`${words(key)}: ${typeof value === 'number' ? price(value) : String(value)}`)
  }
  return parts.join(' · ')
}

const exclusions = (item: EvidenceItem): string =>
  Object.entries(item.excluded.reduce<Record<string, number>>((counts, e) => ({ ...counts, [e.reason]: (counts[e.reason] ?? 0) + 1 }), {}))
    .map(([reason, count]) => `${reason} (${count})`)
    .join(', ')

/** One evidence item: its records with observed and received times and age at entry, or a missing marker with the reason. */
export function PaperEvidenceItem({ item }: { item: EvidenceItem }) {
  const heading = item.status === 'present' ? `${item.records.length} kept, newest ${age(item.newest_age_s)} before entry` : `missing: ${item.reason}`
  return (
    <li className={item.status === 'present' ? styles.item : `${styles.item} ${styles.missing}`}>
      <details>
        <summary><strong>{item.label}</strong> · {heading}{item.excluded_count ? ` · ${item.excluded_count} excluded` : ''}</summary>
        <p>Source: {item.source ?? 'not recorded'}{item.coverage ? `. ${item.coverage}` : ''}</p>
        {item.records.slice(0, SHOWN).map((record, index) => (
          <p key={`${String(record.id ?? '')}-${index}`} className={styles.record}>
            Observed {exactTime(record.observed_at)} · received {exactTime(record.received_at)} · {age(record.age_s)} before entry
            {detail(record) ? ` · ${detail(record)}` : ''}
          </p>
        ))}
        {item.records.length > SHOWN && <p>{item.records.length - SHOWN} more records in the raw record.</p>}
        {item.excluded.length > 0 && <p>Excluded: {exclusions(item)}{item.excluded_count > item.excluded.length ? `, and ${item.excluded_count - item.excluded.length} more` : ''}.</p>}
      </details>
    </li>
  )
}
