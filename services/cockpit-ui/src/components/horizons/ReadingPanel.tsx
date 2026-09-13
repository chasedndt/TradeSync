import { useStartHorizonReading } from '../../api/hooks/useHorizons'
import type { HorizonReading } from '../../api/horizonTypes'
import { since } from '../ledger/format'
import { LinkedText, type LinkTarget } from './LinkedText'
import styles from './ReadingPanel.module.css'

const STATUS: Record<HorizonReading['status'], string> = {
  none: 'Hermes has not read this market yet.',
  running: 'Hermes is reading the measured numbers…',
  ok: '',
  refused: 'The harness boundary refused the answer.',
  unavailable: 'Hermes did not answer.',
  not_configured: 'The Hermes gateway is not configured.',
}

/** Hermes's prose reading of every time frame, from the measured numbers only; each feature name links to its chart. */
export function ReadingPanel({ symbol, reading, targets, onPickFeature }: {
  symbol: string
  reading: HorizonReading
  targets: LinkTarget[]
  onPickFeature: (key: string) => void
}) {
  const start = useStartHorizonReading(symbol)
  const running = reading.status === 'running' || start.isPending
  const paragraphs = (reading.content ?? '').split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)

  return (
    <section className={`panel ${styles.panel}`} aria-labelledby="hermes-reading-title">
      <div className="panel-heading">
        <div>
          <h3 id="hermes-reading-title">Hermes reading</h3>
          <p>drafted from the numbers on this page only · advisory · filed in quarantine with a receipt · feature names link to their charts</p>
        </div>
        <button type="button" className="chip" disabled={running} onClick={() => start.mutate()}>
          {running ? 'reading…' : reading.status === 'ok' ? 'read again' : 'ask Hermes'}
        </button>
      </div>
      <div className={styles.body}>
        {reading.status !== 'ok' && <p className={reading.status === 'running' ? styles.muted : styles.status}>{STATUS[reading.status]}{reading.detail ? ` (${reading.detail})` : ''}</p>}
        {paragraphs.map((p, i) => <p key={i}><LinkedText text={p} targets={targets} onPick={onPickFeature} /></p>)}
        {reading.status === 'ok' && (
          <p className={styles.muted}>{reading.model ?? 'hermes'} · {reading.elapsed_ms ? `${Math.round(reading.elapsed_ms / 1000)}s` : ''} · {since(reading.finished_at)}</p>
        )}
        {start.error && <p className={styles.status}>{(start.error as Error).message}</p>}
      </div>
    </section>
  )
}
