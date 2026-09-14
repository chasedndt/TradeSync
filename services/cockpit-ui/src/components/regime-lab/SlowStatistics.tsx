import { useState } from 'react'
import { EvidenceCards } from '../EvidenceCards'
import { SkillGatePanel } from '../SkillGatePanel'
import styles from './SlowStatistics.module.css'

/** The skill gate and the evidence cards: slow statistics measured in the background, collapsed until opened. */
export function SlowStatistics({ symbol }: { symbol: string }) {
  const [open, setOpen] = useState(false)
  return (
    <details className={styles.slow} open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className={styles.summary}>
        Skill gate and evidence cards
        <small>{symbol} · measured in the background, refreshed every 10 minutes while viewed</small>
      </summary>
      {open && (
        <div className={styles.body}>
          <SkillGatePanel symbol={symbol} />
          <EvidenceCards symbol={symbol} />
        </div>
      )}
    </details>
  )
}
