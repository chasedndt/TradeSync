import { useStartHorizonReading } from '../../api/hooks/useHorizons'
import type { BandKey, BandReading as Reading } from '../../api/horizonTypes'
import { LinkedText, type LinkTarget } from './LinkedText'
import { clock } from './timeframeText'
import styles from './BandReading.module.css'

const FAILED: Partial<Record<Reading['status'], string>> = {
  refused: 'The harness boundary refused the last answer.',
  unavailable: 'Hermes did not answer the last request.',
  not_configured: 'The Hermes gateway is not configured.',
}

interface Props {
  symbol: string
  band: BandKey
  label: string
  reading: Reading
  measuredAt?: string
  targets: LinkTarget[]
  onPick: (key: string) => void
}

/**
 * Hermes's reading of one time frame, with the exact time it was read and the
 * measurement it read. A reading older than the latest measurement says so, and
 * the last good reading stays visible while a new one runs or fails.
 */
export function BandReading({ symbol, band, label, reading, measuredAt, targets, onPick }: Props) {
  const start = useStartHorizonReading(symbol)
  const running = reading.status === 'running' || start.isPending
  const paragraphs = (reading.content ?? '').split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)
  const stale = Boolean(reading.measured_at && measuredAt && new Date(reading.measured_at).getTime() < new Date(measuredAt).getTime())
  const failed = reading.attempt ? FAILED[reading.attempt.status] : undefined

  return (
    <section className={`panel ${styles.panel}`} aria-labelledby={`reading-${band}`}>
      <header className={styles.head}>
        <div>
          <h3 id={`reading-${band}`}>Hermes reading · {label}</h3>
          <p className={styles.meta}>
            {reading.finished_at ? (
              <>Read <time dateTime={reading.finished_at}>{clock(reading.finished_at)}</time> from the measurement of{' '}
                <time dateTime={reading.measured_at}>{clock(reading.measured_at)}</time>{reading.model ? ` · ${reading.model}` : ''}</>
            ) : 'Not read yet'}
          </p>
        </div>
        <button type="button" className="chip" disabled={running} onClick={() => start.mutate(band)}>
          {running ? 'reading…' : paragraphs.length ? 'read again' : 'ask Hermes'}
        </button>
      </header>
      {stale && !running && (
        <p className={styles.stale}>Re-measured at {clock(measuredAt)}, after this reading. Read again to bring it up to date.</p>
      )}
      {running && <p className={styles.muted}>Hermes is reading the {label.toLowerCase()} numbers (started {clock(reading.attempt?.started_at)})…</p>}
      {!running && failed && (
        <p className={styles.warn}>{failed}{reading.attempt?.detail ? ` (${reading.attempt.detail})` : ''}{paragraphs.length ? ' The last good reading is shown.' : ''}</p>
      )}
      <div className={styles.body}>
        {paragraphs.map((p, i) => <p key={i}><LinkedText text={p} targets={targets} onPick={onPick} /></p>)}
        {!paragraphs.length && !running && (
          <p className={styles.muted}>Ask Hermes to read this time frame's measured numbers. The reading is advisory and filed in quarantine with a receipt.</p>
        )}
      </div>
      {start.error && <p className={styles.warn}>{(start.error as Error).message}</p>}
    </section>
  )
}
