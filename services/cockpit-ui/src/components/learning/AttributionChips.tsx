import type { AttributedReading } from '../../api/learningTypes'
import styles from './AttributionChips.module.css'

const MARK = { misled: '✕', supported: '✓', neutral: '·' } as const

function pull(reading: AttributedReading): string {
  const positive = reading.contribution > 0
  if (reading.role === 'directional') return positive ? 'pointed up' : 'pointed down'
  return positive ? 'favourable' : 'unfavourable'
}

interface AttributionChipsProps {
  readings: AttributedReading[]
  limit?: number
  /** Show readings the result did not judge, for calls whose move stayed inside costs. */
  showNeutral?: boolean
}

/** One decision's readings, largest share first, each marked as having supported or misled the call. */
export function AttributionChips({ readings, limit = 6, showNeutral = false }: AttributionChipsProps) {
  const shown = readings
    .filter((reading) => showNeutral || reading.verdict !== 'neutral')
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
  if (!shown.length) return null
  const hidden = shown.length - limit

  return (
    <ul className={styles.chips} aria-label="What each reading did">
      {shown.slice(0, limit).map((reading) => (
        <li
          key={`${reading.id}-${reading.role}`}
          className={`${styles.chip} ${styles[reading.verdict]}`}
          title={`${reading.label}: ${reading.verdict}, ${pull(reading)} (${reading.role} contribution ${reading.contribution.toFixed(3)})`}
        >
          <span className={styles.mark} aria-hidden="true">{MARK[reading.verdict]}</span>
          <span className="sr-only">{reading.verdict}:</span>
          <span className={styles.label}>{reading.label}</span>
          <span className={styles.pull}>{pull(reading)}</span>
        </li>
      ))}
      {hidden > 0 && <li className={styles.more}>+{hidden} more</li>}
    </ul>
  )
}
